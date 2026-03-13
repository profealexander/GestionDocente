"""Query skill handler — answers data requests from free text."""

from loguru import logger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.state import clear_query, get_query, set_query, QueryFlow
from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.skills.homework.detector import extract_course
from schoolai.skills.homework.repository import find_grade
from schoolai.skills.query.detector import QueryIntent, extract_intent
from schoolai.skills.query.formatter import format_attendance, format_homework
from schoolai.skills.query.resolver import resolve_attendance, resolve_homework
from schoolai.skills.utils.keyboards import grade_keyboard

from sqlalchemy import select


async def start_query(update: Update, text: str) -> None:
    user_id = update.effective_user.id
    intent = extract_intent(text)
    logger.info(f"[query] user={user_id} type={intent.type} period={intent.period}")

    course_text = extract_course(text)
    grade = None
    if course_text:
        async with async_session() as session:
            grade = await find_grade(session, course_text)

    if not grade:
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()

        set_query(user_id, QueryFlow(intent=intent))
        await update.message.reply_text(
            "¿De qué curso?",
            reply_markup=grade_keyboard(grades, "qry_grade"),
        )
        return

    await _run_query(update.message.reply_text, user_id, intent, grade.id)


async def handle_query_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data.startswith("qry_grade:"):
        parts = data.split(":", 2)
        grade_id = int(parts[1])
        flow = get_query(user_id)
        if not flow:
            await query.edit_message_text("Sesión expirada. Vuelve a hacer la consulta.")
            return
        clear_query(user_id)
        await _run_query(query.edit_message_text, user_id, flow.intent, grade_id)


async def _run_query(reply_fn, user_id: int, intent: QueryIntent, grade_id: int) -> None:
    async with async_session() as session:
        if intent.type == "attendance":
            data = await resolve_attendance(intent, grade_id, session)
            text = format_attendance(data)
        else:
            data = await resolve_homework(intent, grade_id, session)
            text = format_homework(data)

    await reply_fn(text, parse_mode=ParseMode.MARKDOWN)
    logger.info(f"[query] user={user_id} grade={grade_id} done")
