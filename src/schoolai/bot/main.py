from loguru import logger
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from loguru import logger

from schoolai.bot.action_handler import handle_act_callback
from schoolai.bot.attendance_handler import handle_attendance_callback
from schoolai.bot.db_handler import handle_db_callback, handle_db_command, handle_db_text
from schoolai.bot.help_handler import handle_help_back, handle_help_callback, handle_help_command
from schoolai.bot.query_handler import handle_query_callback
from schoolai.bot.handlers import handle_text, handle_voice
from schoolai.bot.state import cleanup_stale, clear_attendance, clear_db_flow, clear_pending, clear_query, get_db_flow
from schoolai.config import settings


async def _handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    clear_db_flow(user_id)
    clear_attendance(user_id)
    clear_pending(user_id)
    clear_query(user_id)
    await update.message.reply_text("Operación cancelada.")


async def _run_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    removed = cleanup_stale()
    if removed:
        logger.info(f"[TTL] cleanup removed {removed} stale states")


class _DbFlowFilter(filters.MessageFilter):
    """Only matches messages while a /db flow is active for the sender."""
    def filter(self, message) -> bool:
        user = message.from_user
        return user is not None and get_db_flow(user.id) is not None


async def _debug_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all: logs any callback not handled by specific handlers."""
    q = update.callback_query
    await q.answer()
    logger.warning(f"[unhandled callback] data={q.data!r} user={update.effective_user.id}")


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"[bot error] {context.error}", exc_info=context.error)


def run() -> None:
    logger.info("Starting SchoolAI bot...")
    request = HTTPXRequest(connect_timeout=20, read_timeout=20, write_timeout=20)
    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .request(request)
        .build()
    )

    # TTL cleanup cada 10 minutos
    app.job_queue.run_repeating(_run_cleanup, interval=600, first=600)

    app.add_error_handler(_error_handler)

    # Cancelar cualquier flujo activo
    app.add_handler(CommandHandler("cancelar", _handle_cancel))
    # Help
    app.add_handler(CommandHandler("ayuda", handle_help_command))
    app.add_handler(CallbackQueryHandler(handle_help_back, pattern=r"^help:back$"))
    app.add_handler(CallbackQueryHandler(handle_help_callback, pattern=r"^help:"))
    # DB skill
    app.add_handler(CommandHandler("db", handle_db_command))
    app.add_handler(CallbackQueryHandler(handle_db_callback, pattern=r"^db_"))
    # Attendance skill
    app.add_handler(CallbackQueryHandler(handle_attendance_callback, pattern=r"^att_"))
    # Query skill
    app.add_handler(CallbackQueryHandler(handle_query_callback, pattern=r"^qry_"))
    # Action handler (LLM extractor course selection)
    app.add_handler(CallbackQueryHandler(handle_act_callback, pattern=r"^act_grade:"))
    # Catch-all for unhandled callbacks (debug)
    app.add_handler(CallbackQueryHandler(_debug_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & _DbFlowFilter(), handle_db_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    logger.info("Bot running. Press Ctrl+C to stop.")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    run()
