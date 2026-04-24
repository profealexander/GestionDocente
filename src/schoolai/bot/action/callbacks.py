"""Callbacks de selección de curso, confirmación y acciones de curso."""

from __future__ import annotations

from datetime import date

from telegram.constants import ParseMode

from schoolai.bot.action.attendance import _save_attendance
from schoolai.bot.action.cache import pop_pending
from schoolai.bot.action.homework import _save_homework
from schoolai.bot.action.homework_report import _save_homework_report
from schoolai.bot.action.query import (
    _build_query_intent,
    _query_my_courses_attendance,
    _query_my_courses_homework,
)
from schoolai.bot.callback_router import callback_router
from schoolai.bot.state import (
    PendingCourseContext,
    pop_pending_confirm,
    set_course_context,
)
from schoolai.db.connection import get_db_session
from schoolai.skills.query.detector import QueryIntent


@callback_router.register("act_confirm:")
async def handle_act_confirm_callback(update, context) -> None:
    """Handles act_confirm:yes|no — confirma o cancela una acción extraída por LLM."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    choice = query.data.split(":")[1]

    pc = pop_pending_confirm(user_id)

    if choice == "no" or pc is None:
        await query.edit_message_text("❌ Operación cancelada.")
        return

    await query.edit_message_reply_markup(reply_markup=None)

    async def _reply(text, **kw):
        await context.bot.send_message(pc.chat_id, text, **kw)

    if pc.intent == "attendance":
        await _save_attendance(_reply, user_id, pc.data, pc.chat_id)
    elif pc.intent == "homework":
        await _save_homework(_reply, user_id, pc.data)


@callback_router.register("course_action:")
async def handle_course_action_callback(update, context) -> None:
    """Handles course_action:{action}:{abbrev} — triggered from the course-only menu."""
    from schoolai.skills.utils.courses import _ABBREV_TO_NAME, course_abbrev_map

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    _, action, abbrev = query.data.split(":", 2)

    grade_id = course_abbrev_map.get(abbrev)
    if not grade_id:
        await query.edit_message_text("Curso no encontrado.")
        return

    grade_name = _ABBREV_TO_NAME.get(abbrev, abbrev.upper())
    await query.edit_message_reply_markup(reply_markup=None)

    if action in ("hw", "att", "compliance"):
        intent_map = {"hw": "homework", "att": "attendance", "compliance": "homework_report"}
        ctx = PendingCourseContext(
            course_abbrev=abbrev,
            grade_id=grade_id,
            grade_name=grade_name,
            pending_intent=intent_map[action],
        )
        set_course_context(user_id, ctx)
        prompts = {
            "hw": (
                f"¿Cuál es la tarea para <b>{grade_name.title()}</b>?\n"
                "<i>Indica también la materia.</i>"
            ),
            "att": f"¿Quién faltó hoy en <b>{grade_name.title()}</b>?",
            "compliance": (
                f"¿Quién no entregó en <b>{grade_name.title()}</b>?\n"
                "<i>Puedes indicar la tarea si aplica.</i>"
            ),
        }
        await context.bot.send_message(chat_id, prompts[action], parse_mode=ParseMode.HTML)

    elif action == "query_hw":
        intent = _build_query_intent("trimester")
        intent.type = "homework"
        from schoolai.bot.query_handler import _run_query

        await _run_query(
            lambda t, **kw: context.bot.send_message(chat_id, t, **kw),
            user_id,
            intent,
            grade_id,
        )

    elif action == "query_att":
        today = date.today()
        intent = QueryIntent(type="attendance", period="day", period_start=today, period_end=today)
        from schoolai.bot.query_handler import _run_query

        await _run_query(
            lambda t, **kw: context.bot.send_message(chat_id, t, **kw),
            user_id,
            intent,
            grade_id,
        )

    elif action == "pick":
        from schoolai.bot.handlers import _show_course_action_menu

        await _show_course_action_menu(update, (abbrev, grade_id, grade_name))


@callback_router.register("act_grade:")
async def handle_act_callback(update, context) -> None:
    """Maneja selección de curso cuando el extractor no lo detectó."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    parts = data.split(":", 2)
    raw_id = parts[1]
    grade_name = parts[2] if len(parts) > 2 else parts[1]

    result = pop_pending(user_id)
    if not result:
        await query.edit_message_text("Sesión expirada. Vuelve a enviar el mensaje.")
        return

    if raw_id == "all_mine":
        if result.intent == "query" and result.data.query_type == "attendance":
            intent_obj = _build_query_intent(result.data.period, result.data.subject)
            intent_obj.type = "attendance"
            await _query_my_courses_attendance(query.edit_message_text, user_id, intent_obj)
        elif result.intent == "query" and result.data.query_type == "homework":
            await _query_my_courses_homework(query.edit_message_text, user_id, result.data)
        else:
            await query.edit_message_text("Opción no disponible para esta consulta.")
        return

    if result.intent == "attendance":
        result.data.course = grade_name
        result.data.complete = True
        await _save_attendance(query.edit_message_text, user_id, result.data, query.message.chat_id)
    elif result.intent == "homework":
        result.data.course = grade_name
        result.data.complete = True
        await _save_homework(query.edit_message_text, user_id, result.data)
    elif result.intent == "homework_report":
        result.data.course = grade_name
        result.data.complete = True
        await _save_homework_report(
            query.edit_message_text,
            user_id,
            result.data,
            query.message.chat_id,
        )
    elif result.intent == "query":
        from schoolai.bot.query_handler import _run_query
        from schoolai.skills.homework.repository import find_grade as _find_grade

        intent_obj = _build_query_intent(result.data.period, result.data.subject)
        intent_obj.type = result.data.query_type
        async with get_db_session() as session:
            grade = await _find_grade(session, grade_name)
        if grade:
            await _run_query(query.edit_message_text, user_id, intent_obj, grade.id)
        else:
            await query.edit_message_text(f"No encontré el curso {grade_name}.")
