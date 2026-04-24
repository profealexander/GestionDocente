"""Bot Agente — GLM-4.7-Flash como único punto de entrada.

Todos los mensajes van directo a OrchestratorSkill sin pipeline regex.
Sin callbacks de cuotas/asistencia/jornada — solo texto y voz.

Token: TELEGRAM_BOT_TOKEN_AGENTE en .env
"""

from __future__ import annotations

import html
import sys

try:
    import asyncio

    import uvloop

    uvloop.install()
    asyncio.set_event_loop(asyncio.new_event_loop())
except ImportError:
    pass

from loguru import logger
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from schoolai.bot.context_handler import handle_context_text_command, handle_context_upload
from schoolai.bot.jornada_handler import handle_horario_callback, handle_horario_command

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
    from schoolai.bot.jornada_handler import _horario_interceptor
    from schoolai.skills.orchestrator.skill import OrchestratorSkill

    user = update.effective_user
    if not is_allowed(user.id):
        logger.warning(f"[agente] usuario no autorizado: {user.id}")
        return

    text = update.message.text.strip()
    logger.info(f"[agente] user={user.id}: {text[:200]}")

    if await _horario_interceptor(update, user.id):
        return

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
                f"Mensaje: <code>{html.escape(msg[:200])}</code>\n"
                f"Error: <code>{html.escape(str(context.error))}</code>",
                parse_mode="HTML",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[agente] failed to send error notification to admin: {exc}")


# ── Post-init ─────────────────────────────────────────────────────────────────


async def _post_init(app) -> None:
    from schoolai.bot.startup import common_post_init

    await common_post_init(app, register_reminders=True, log_label="agente")
    logger.info("[agente] listo — OrchestratorSkill activo")


# ── Logging ───────────────────────────────────────────────────────────────────


def _setup_logging() -> None:
    from schoolai.logging import setup_logging
    setup_logging("bot-agente")


# ── Entry point ───────────────────────────────────────────────────────────────


def run_agente() -> None:
    _setup_logging()

    from schoolai.bot.singleton import singleton_guard

    singleton_guard("agente")

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
    app.add_handler(CommandHandler("horario", handle_horario_command))
    app.add_handler(CallbackQueryHandler(handle_horario_callback, pattern=r"^hor_day:"))
    app.add_handler(CommandHandler("contexto", handle_context_text_command))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_context_upload))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, _handle_voice))

    logger.info("Bot Agente running. Press Ctrl+C to stop.")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    run_agente()
