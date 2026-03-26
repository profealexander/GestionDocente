"""Bot Agente — GLM-4.7-Flash como único punto de entrada.

Todos los mensajes van directo a OrchestratorSkill sin pipeline regex.
Sin callbacks de cuotas/asistencia/jornada — solo texto y voz.

Token: TELEGRAM_BOT_TOKEN_AGENTE en .env
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import uvloop

    uvloop.install()
except ImportError:
    pass

from loguru import logger
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from schoolai.config import settings

# ── Handlers ──────────────────────────────────────────────────────────────────


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hola, soy SchoolAI Agente.\n"
        "Puedo registrar asistencia, tareas, cuotas y responder consultas.\n"
        "Escríbeme en lenguaje natural.",
    )


async def _handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Operación cancelada.")


async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from schoolai.bot.handlers import is_allowed
    from schoolai.skills.orchestrator.skill import OrchestratorSkill

    user = update.effective_user
    if not is_allowed(user.id):
        logger.warning(f"[agente] usuario no autorizado: {user.id}")
        return

    text = update.message.text.strip()
    logger.info(f"[agente] user={user.id}: {text[:200]}")

    skill = OrchestratorSkill()
    await skill.handle(update, user.id, text)


async def _handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from schoolai.bot.handlers import is_allowed
    from schoolai.bot.transcription import transcribe
    from schoolai.skills.orchestrator.skill import OrchestratorSkill

    user = update.effective_user
    if not is_allowed(user.id):
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
        logger.info(f"[agente:voice] {user.id}: {text[:80]}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"[agente:voice] error: {e}")
        await update.message.reply_text("Error al transcribir. Intenta enviarlo como texto.")
        return

    await update.message.reply_text(f'Escuché: "{text}"')
    skill = OrchestratorSkill()
    await skill.handle(update, user.id, text)


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"[agente error] {context.error}", exc_info=context.error)
    if settings.admin_telegram_id:
        try:
            user = getattr(update, "effective_user", None)
            msg = getattr(getattr(update, "message", None), "text", "—")
            await context.bot.send_message(
                settings.admin_telegram_id,
                f"⚠️ <b>Error en SchoolAI Agente</b>\n"
                f"Usuario: {user.id if user else '?'}\n"
                f"Mensaje: <code>{msg[:200]}</code>\n"
                f"Error: <code>{context.error}</code>",
                parse_mode="HTML",
            )
        except Exception:  # noqa: BLE001
            pass


# ── Post-init ─────────────────────────────────────────────────────────────────


async def _post_init(app) -> None:
    from schoolai.bot.state import init_redis
    from schoolai.skills.utils.courses import load_course_map

    init_redis(settings.redis_url)
    await load_course_map()
    logger.info("[agente] listo — OrchestratorSkill activo")


# ── Logging ───────────────────────────────────────────────────────────────────


def _setup_logging() -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    )
    logger.add(
        log_dir / "agente_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {message}",
    )


# ── Entry point ───────────────────────────────────────────────────────────────


def run_agente() -> None:
    _setup_logging()

    token = settings.telegram_bot_token_agente
    if not token:
        logger.error("[agente] TELEGRAM_BOT_TOKEN_AGENTE no configurado en .env")
        sys.exit(1)

    if not settings.zai_api_key:
        logger.warning("[agente] ZAI_API_KEY no configurado — OrchestratorSkill fallará")

    logger.info("Starting SchoolAI Agente [GLM-4.7-Flash]...")

    request = HTTPXRequest(connect_timeout=20, read_timeout=20, write_timeout=20)
    app = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .concurrent_updates(32)
        .post_init(_post_init)
        .build()
    )

    app.add_error_handler(_error_handler)
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("cancelar", _handle_cancel))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, _handle_voice))

    logger.info("Bot Agente running. Press Ctrl+C to stop.")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message"],
    )


if __name__ == "__main__":
    run_agente()
