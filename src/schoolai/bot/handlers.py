from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from schoolai.bot.action_handler import handle_extraction, resolve_selection_text
from schoolai.bot.mode import is_jornada
from schoolai.bot.state import get_jornada
from schoolai.bot.transcription import transcribe
from schoolai.bot.whatsapp_handler import handle_wa_setup_text
from schoolai.config import settings
from schoolai.skills.extractor.llm import _ABBREV_TO_NAME, _NAME_TO_ABBREV, course_abbrev_map, extract
from schoolai.skills.extractor.rules import extract_fallback
from schoolai.skills.ia.agent import chat
from schoolai.skills.ia.history import get as get_history, append as append_history

# Teclas de acceso rápido para iniciar Modo Jornada
_JORNADA_TRIGGERS = {"j", "J", "1", "jornada", "Jornada", "iniciar", "Iniciar", "📅 Jornada"}

JORNADA_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("📅 Jornada")]],
    resize_keyboard=True,
    is_persistent=True,
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


def _detect_course_only(text: str) -> tuple[str, int, str] | None:
    """Returns (abbrev, grade_id, grade_name) when the message is just a course reference."""
    t = text.strip()

    # Path 1: verbal name  ("primero bt", "octavo egb")
    canonical = t.upper()
    abbrev = _NAME_TO_ABBREV.get(canonical)
    if abbrev and abbrev in course_abbrev_map:
        return abbrev, course_abbrev_map[abbrev], canonical

    # Path 2: abbreviation ("1bt", "8egb", "prep")
    abbrev = t.lower().replace(" ", "")
    if abbrev in course_abbrev_map:
        grade_name = _ABBREV_TO_NAME.get(abbrev, abbrev.upper())
        return abbrev, course_abbrev_map[abbrev], grade_name

    return None


async def _show_course_action_menu(update: Update, course_info: tuple) -> None:
    abbrev, _grade_id, grade_name = course_info
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Registrar tarea",       callback_data=f"course_action:hw:{abbrev}"),
            InlineKeyboardButton("✅ Registrar asistencia",  callback_data=f"course_action:att:{abbrev}"),
        ],
        [
            InlineKeyboardButton("📋 Ver tareas",            callback_data=f"course_action:query_hw:{abbrev}"),
            InlineKeyboardButton("📊 Cumplimiento",          callback_data=f"course_action:compliance:{abbrev}"),
        ],
        [
            InlineKeyboardButton("📈 Ver asistencia hoy",   callback_data=f"course_action:query_att:{abbrev}"),
        ],
    ])
    await update.message.reply_text(
        f"¿Qué deseas hacer con <b>{grade_name.title()}</b>?",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def _dispatch(update: Update, user_id: int, text: str) -> None:
    # Atajo para iniciar Modo Jornada — funciona en ambos modos
    if text in _JORNADA_TRIGGERS:
        from schoolai.bot.jornada_handler import handle_jornada_command
        await handle_jornada_command(update, None)
        return

    if is_jornada():
        session = get_jornada(user_id)
        if not session or session.status == "done":
            await update.message.reply_text(
                "Toca el botón o escribe *j* para iniciar tu jornada.",
                parse_mode="Markdown",
                reply_markup=JORNADA_KEYBOARD,
            )
            return

    # Estados pendientes: si el usuario escribió un número (1, 2, 3...)
    if await resolve_selection_text(update, user_id):
        return

    # Flujo de setup WhatsApp (colección de phone)
    if await handle_wa_setup_text(update):
        return

    # Filtrar marcadores internos antes de pasarlo al extractor —
    # "[X procesado]" es útil para el chat IA pero confunde al extractor LLM.
    history = [
        m for m in get_history(user_id)
        if not (m["role"] == "assistant" and m["content"].startswith("[") and m["content"].endswith("procesado]"))
    ]

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
        # Modo Libre: if message is only a course name, show action menu
        if not is_jornada():
            course_info = _detect_course_only(text)
            if course_info:
                await _show_course_action_menu(update, course_info)
                return
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
