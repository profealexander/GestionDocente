from loguru import logger
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from schoolai.bot.attendance_handler import handle_attendance_callback
from schoolai.bot.db_handler import handle_db_callback, handle_db_command, handle_db_text
from schoolai.bot.handlers import handle_text, handle_voice
from schoolai.config import settings


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

    app.add_error_handler(_error_handler)

    # DB skill
    app.add_handler(CommandHandler("db", handle_db_command))
    app.add_handler(CallbackQueryHandler(handle_db_callback, pattern=r"^db_"))
    # Attendance skill
    app.add_handler(CallbackQueryHandler(handle_attendance_callback, pattern=r"^att_"))
    # Catch-all for unhandled callbacks (debug)
    app.add_handler(CallbackQueryHandler(_debug_callback))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    logger.info("Bot running. Press Ctrl+C to stop.")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    run()
