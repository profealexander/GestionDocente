from loguru import logger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.attendance_handler import start_attendance
from schoolai.bot.db_handler import handle_db_text
from schoolai.bot.state import PendingHomework, clear_pending, get_attendance, get_db_flow, get_pending, set_pending
from schoolai.bot.transcription import transcribe
from schoolai.config import settings
from schoolai.db.connection import async_session
from schoolai.bot.router import classify
from schoolai.skills.attendance.detector import is_attendance_message, is_attendance_message_fuzzy
from schoolai.skills.homework.detector import is_homework_message
from schoolai.skills.homework.pre_agent import process, save_with_subject
from schoolai.skills.ia.agent import chat


def is_allowed(user_id: int) -> bool:
    allowed = settings.allowed_user_ids
    return not allowed or user_id in allowed


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        logger.warning(f"Unauthorized user {user.id}")
        return

    text = update.message.text.strip()
    logger.info(f"[text] {user.id}: {text[:80]}")

    # DB skill takes priority when flow is active
    if get_db_flow(user.id):
        await handle_db_text(update, context)
        return

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
    # 1 — Pending state takes priority
    if get_attendance(user_id):
        logger.info(f"[dispatch] user={user_id} → attendance (pending)")
        await start_attendance(update, text)
        return

    if get_pending(user_id):
        logger.info(f"[dispatch] user={user_id} → homework (pending)")
        await _run_homework_agent(update, user_id, text)
        return

    # 2 — Exact keyword detection (fast, no API)
    if is_attendance_message(text):
        logger.info(f"[dispatch] user={user_id} → attendance (exact)")
        await start_attendance(update, text)
        return

    if is_homework_message(text):
        logger.info(f"[dispatch] user={user_id} → homework (exact)")
        await _run_homework_agent(update, user_id, text)
        return

    # 3 — Fuzzy keyword detection (catches typos)
    if is_attendance_message_fuzzy(text):
        logger.info(f"[dispatch] user={user_id} → attendance (fuzzy)")
        await start_attendance(update, text)
        return

    # 4 — GLM classifier as final fallback
    intent = await classify(text)
    if intent == "attendance":
        logger.info(f"[dispatch] user={user_id} → attendance (glm)")
        await start_attendance(update, text)
        return

    if intent == "homework":
        logger.info(f"[dispatch] user={user_id} → homework (glm)")
        await _run_homework_agent(update, user_id, text)
        return

    logger.info(f"[dispatch] user={user_id} → ia")
    await _run_ia_skill(update, user_id, text)


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


async def _run_homework_agent(update: Update, user_id: int, text: str) -> None:
    pending = get_pending(user_id)

    async with async_session() as session:
        if pending:
            result = await save_with_subject(
                text=pending.text,
                subject_text=text,
                grade_id=pending.grade_id,
                grade_name=pending.grade_name,
                delivery=pending.delivery,
                session=session,
            )
        else:
            result = await process(text, session)

    if result.waiting_for_subject:
        set_pending(user_id, PendingHomework(
            text=text,
            grade_id=result.pending_grade_id,
            grade_name=result.pending_grade_name,
            delivery=result.pending_delivery,
        ))
    else:
        clear_pending(user_id)

    await update.message.reply_text(result.message, parse_mode=ParseMode.MARKDOWN)
