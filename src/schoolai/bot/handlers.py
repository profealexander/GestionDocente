from loguru import logger
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes

from schoolai.bot.transcription import transcribe
from schoolai.config import settings
from schoolai.skills.ia.agent import chat

# Teclas de acceso rápido para iniciar Modo Jornada
_JORNADA_TRIGGERS = {"j", "J", "1", "jornada", "Jornada", "📅 Jornada"}

JORNADA_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("📅 Jornada")]],
    resize_keyboard=True,
    input_field_placeholder="Escribe o toca 📅 Jornada...",
)
REMOVE_KEYBOARD = ReplyKeyboardRemove()


def is_allowed(user_id: int) -> bool:
    allowed = settings.allowed_user_ids
    return not allowed or user_id in allowed


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        logger.warning(f"Unauthorized user {user.id}")
        return

    text = update.message.text.strip()
    logger.info(f"[text] user={user.id} (@{user.username}): {text[:200]}")
    logger.debug(f"[text:full] user={user.id}: {text}")

    await _dispatch(update, user.id, text)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        logger.warning(f"Unauthorized user {user.id}")
        return

    if not settings.groq_api_key:
        await update.message.reply_text("Transcripción de audio no configurada.")
        return

    await update.message.reply_text("Transcribiendo audio...")

    voice = update.message.voice or update.message.audio
    tg_file = await context.bot.get_file(voice.file_id)
    audio_bytes = await tg_file.download_as_bytearray()

    try:
        text = await transcribe(bytes(audio_bytes), "audio.ogg", settings.groq_api_key)
        logger.info(f"[voice] {user.id}: {text[:80]}")
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        await update.message.reply_text("Error al transcribir el audio. Intenta enviarlo como texto.")
        return

    await update.message.reply_text(f'Escuché: "{text}"')
    await _dispatch(update, user.id, text)


async def _dispatch(update: Update, user_id: int, text: str) -> None:
    from schoolai.bot.mode import is_jornada
    from schoolai.bot.state import get_jornada
    if is_jornada():
        session = get_jornada(user_id)
        # Atajo de teclado para iniciar jornada
        if text in _JORNADA_TRIGGERS:
            from schoolai.bot.jornada_handler import handle_jornada_command
            await handle_jornada_command(update, None)
            return
        if not session or session.status == "done":
            await update.message.reply_text(
                "Toca el botón o escribe *j* para iniciar tu jornada.",
                parse_mode="Markdown",
                reply_markup=JORNADA_KEYBOARD,
            )
            return
    from schoolai.skills.extractor.llm import extract
    from schoolai.skills.extractor.rules import extract_fallback
    from schoolai.skills.ia.history import get as get_history, append as append_history
    from schoolai.bot.action_handler import handle_extraction, resolve_selection_text

    # Estados pendientes: si el usuario escribió un número (1, 2, 3...)
    if await resolve_selection_text(update, user_id):
        return

    # Obtener historial para contexto
    history = get_history(user_id)

    # Extraer intent y entidades con LLM
    result = await extract(text, history)

    # Guardar en historial
    append_history(user_id, "user", text)

    if result is None:
        # LLM falló — intentar con reglas básicas antes de dar error
        result = extract_fallback(text)
        if result is not None:
            logger.info(f"[fallback] intent={result.intent} user={user_id}")
        else:
            await update.message.reply_text(
                "No pude interpretar el mensaje. ¿Puedes reformularlo?\n"
                "Ejemplo: _\"Recalde no asistió el viernes, décimo EGB\"_",
                parse_mode="Markdown",
            )
            return

    if result.intent == "chat":
        await _run_ia_skill(update, user_id, text)
        return

    await handle_extraction(update, user_id, result)
    append_history(user_id, "assistant", f"[{result.intent} procesado]")


async def _run_ia_skill(update: Update, user_id: int, text: str) -> None:
    sent = await update.message.reply_text("...")
    buffer = []
    last_len = 0

    async def send_chunk(delta: str) -> None:
        nonlocal last_len
        buffer.append(delta)
        current = "".join(buffer)
        # Update message every 20 new characters to avoid Telegram rate limits
        if len(current) - last_len >= 20:
            last_len = len(current)
            try:
                await sent.edit_text(current)
            except Exception:
                pass

    await chat(user_id, text, send_chunk)

    # Final edit with complete response
    final = "".join(buffer).strip()
    if final:
        try:
            await sent.edit_text(final)
        except Exception:
            pass
