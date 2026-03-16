import sys
from pathlib import Path

try:
    import uvloop
    uvloop.install()
except ImportError:
    pass  # uvloop no disponible (Windows/CI)

from loguru import logger
from telegram import Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from schoolai.bot.action_handler import handle_act_callback, handle_course_action_callback, handle_selection_callback
from schoolai.bot.whatsapp_handler import handle_wa_notify_callback
from schoolai.bot.attendance_handler import handle_attendance_callback
from schoolai.bot.db_handler import handle_db_callback, handle_db_command, handle_db_text
from schoolai.bot.help_handler import handle_help_back, handle_help_callback, handle_help_command
from schoolai.bot.handlers import handle_text, handle_voice, JORNADA_KEYBOARD
from schoolai.bot.jornada_handler import handle_jornada_callback, handle_jornada_command, job_morning_notify
from schoolai.bot.position_handler import handle_position_callback, handle_position_text
from schoolai.bot.schedule_handler import handle_schedule_callback, handle_schedule_text
from schoolai.bot.state import (
    cleanup_stale, clear_attendance, clear_course_context, clear_db_flow, clear_jornada,
    clear_position_flow, clear_schedule_flow, clear_selection, clear_wa_notification, clear_wa_setup,
    get_db_flow, get_position_flow, get_schedule_flow,
    clear_jornada_all_stale,
)
from schoolai.bot.mode import set_mode
from schoolai.config import settings


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from schoolai.bot.mode import is_jornada
    if is_jornada():
        await update.message.reply_text(
            "¡Hola! Toca *📅 Jornada* o escribe *j* para iniciar tu jornada.",
            parse_mode="Markdown",
            reply_markup=JORNADA_KEYBOARD,
        )
    else:
        await update.message.reply_text(
            "¡Hola! Estoy listo para ayudarte.",
        )


async def _handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from schoolai.bot.mode import is_jornada
    user_id = update.effective_user.id
    clear_db_flow(user_id)
    clear_attendance(user_id)
    clear_selection(user_id)
    clear_schedule_flow(user_id)
    clear_position_flow(user_id)
    clear_jornada(user_id)
    clear_course_context(user_id)
    clear_wa_notification(user_id)
    clear_wa_setup(user_id)
    if is_jornada():
        await update.message.reply_text("Operación cancelada.", reply_markup=JORNADA_KEYBOARD)
    else:
        await update.message.reply_text("Operación cancelada.")


async def _run_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    removed = cleanup_stale()
    removed += clear_jornada_all_stale()
    if removed:
        logger.info(f"[TTL] cleanup removed {removed} stale states")


class _DbFlowFilter(filters.MessageFilter):
    """Matches messages while a /db or schedule flow is active for the sender."""
    def filter(self, message) -> bool:
        user = message.from_user
        if user is None:
            return False
        return (
            get_db_flow(user.id) is not None
            or get_schedule_flow(user.id) is not None
            or get_position_flow(user.id) is not None
        )


async def _debug_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all: logs any callback not handled by specific handlers."""
    q = update.callback_query
    await q.answer()
    logger.warning(f"[unhandled callback] data={q.data!r} user={update.effective_user.id}")


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"[bot error] {context.error}", exc_info=context.error)
    if settings.admin_telegram_id:
        try:
            user = getattr(update, "effective_user", None)
            msg  = getattr(getattr(update, "message", None), "text", "—")
            text = (
                f"⚠️ <b>Error en SchoolAI</b>\n"
                f"Usuario: {user.id if user else '?'} (@{user.username if user else '?'})\n"
                f"Mensaje: <code>{msg[:200]}</code>\n"
                f"Error: <code>{context.error}</code>"
            )
            await context.bot.send_message(settings.admin_telegram_id, text, parse_mode="HTML")
        except Exception:
            pass


async def _handle_db_or_schedule_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Routes text to schedule/position handlers first, falls back to db handler."""
    if await handle_schedule_text(update, context):
        return
    if await handle_position_text(update, context):
        return
    await handle_db_text(update, context)


async def _post_init(app) -> None:
    from schoolai.skills.extractor.llm import load_course_map
    from schoolai.bot.mode import is_jornada
    from schoolai.bot.state import init_redis
    init_redis(settings.redis_url)
    await load_course_map()
    app.bot_data["jornada_mode"] = is_jornada()

    if is_jornada():
        await _send_jornada_keyboard_to_teachers(app.bot)


async def _send_jornada_keyboard_to_teachers(bot) -> None:
    """Al arrancar en modo Jornada, envía el teclado persistente a todos los docentes activos."""
    from sqlalchemy import select
    from schoolai.db.connection import async_session
    from schoolai.db.models.teacher import Teacher
    from schoolai.bot.handlers import JORNADA_KEYBOARD

    try:
        async with async_session() as session:
            teachers = (await session.execute(
                select(Teacher.telegram_id).where(
                    Teacher.is_active.is_(True),
                    Teacher.telegram_id.isnot(None),
                )
            )).scalars().all()

        for telegram_id in teachers:
            try:
                await bot.send_message(
                    chat_id=telegram_id,
                    text="Bot listo. Toca *📅 Jornada* para iniciar.",
                    parse_mode="Markdown",
                    reply_markup=JORNADA_KEYBOARD,
                )
            except Exception as e:
                logger.warning(f"[jornada_init] no se pudo enviar teclado a {telegram_id}: {e}")
    except Exception as e:
        logger.warning(f"[jornada_init] error al cargar docentes: {e}")


def _setup_logging() -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}")
    logger.add(log_dir / "schoolai_{time:YYYY-MM-DD}.log",
               level="DEBUG", rotation="00:00", retention="30 days", compression="gz",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {message}")


def run(dev: bool = False) -> None:
    import datetime as _dt

    _setup_logging()

    if dev and settings.telegram_bot_token_dev:
        token = settings.telegram_bot_token_dev
        set_mode("jornada")
        label = "JORNADA"
    else:
        token = settings.telegram_bot_token
        set_mode("libre")
        label = "LIBRE"

    logger.info(f"Starting SchoolAI bot [Modo {label}]...")
    request = HTTPXRequest(connect_timeout=20, read_timeout=20, write_timeout=20)
    app = (
        ApplicationBuilder()
        .token(token)
        .request(request)
        .post_init(_post_init)
        .build()
    )

    # TTL cleanup cada 10 minutos
    app.job_queue.run_repeating(_run_cleanup, interval=600, first=600)

    app.add_error_handler(_error_handler)

    # ── Handlers comunes a ambos modos ────────────────────────────────────────
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("cancelar", _handle_cancel))
    app.add_handler(CommandHandler("ayuda", handle_help_command))
    app.add_handler(CallbackQueryHandler(handle_help_back, pattern=r"^help:back$"))
    app.add_handler(CallbackQueryHandler(handle_help_callback, pattern=r"^help:"))
    app.add_handler(CommandHandler("db", handle_db_command))
    app.add_handler(CallbackQueryHandler(handle_db_callback, pattern=r"^db_"))
    app.add_handler(CallbackQueryHandler(handle_schedule_callback, pattern=r"^sch_"))
    app.add_handler(CallbackQueryHandler(handle_attendance_callback, pattern=r"^att_"))
    app.add_handler(CallbackQueryHandler(handle_act_callback, pattern=r"^act_grade:"))
    app.add_handler(CallbackQueryHandler(handle_course_action_callback, pattern=r"^course_action:"))
    app.add_handler(CallbackQueryHandler(handle_wa_notify_callback, pattern=r"^wa_notify:"))
    app.add_handler(CallbackQueryHandler(handle_selection_callback, pattern=r"^sel:"))
    app.add_handler(CallbackQueryHandler(handle_position_callback, pattern=r"^pos_"))

    # ── Handlers exclusivos de Modo Jornada ───────────────────────────────────
    if dev:
        app.job_queue.run_daily(job_morning_notify, time=_dt.time(6, 0, 0))
        app.add_handler(CommandHandler("jornada", handle_jornada_command))
        app.add_handler(CallbackQueryHandler(handle_jornada_callback, pattern=r"^jor_"))

    # ── Catch-all callbacks (debug) ───────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(_debug_callback))

    # ── Mensajes de texto ─────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & _DbFlowFilter(), _handle_db_or_schedule_text))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    logger.info("Bot running. Press Ctrl+C to stop.")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
    )


if __name__ == "__main__":
    run()
