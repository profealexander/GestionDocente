"""Handlers de consulta: _build_query_intent, _handle_query y helpers de mis cursos."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from schoolai.bot.action.cache import store_pending
from schoolai.db.connection import get_db_session
from schoolai.db.models.grade import Grade
from schoolai.skills.homework.repository import get_teacher_subject_ids
from schoolai.skills.query.detector import QueryIntent, get_current_trimester
from schoolai.skills.utils.courses import course_abbrev_map
from schoolai.skills.utils.dates import _DAY_NAMES
from schoolai.skills.utils.dates import parse_date as _parse_date
from schoolai.skills.utils.keyboards import grade_keyboard
from schoolai.skills.utils.schema import ExtractionResult, QueryExtract


def _build_query_intent(period: str, subject_filter: str | None = None):
    from schoolai.skills.query.detector import TRIMESTERS

    today = date.today()
    sf = subject_filter

    if period == "today":
        return QueryIntent("homework", "day", today, today, subject_filter=sf)
    if period == "yesterday":
        d = today - timedelta(days=1)
        return QueryIntent("homework", "day", d, d, subject_filter=sf)
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return QueryIntent("homework", "week", start, start + timedelta(days=4), subject_filter=sf)
    if period == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        return QueryIntent("homework", "week", start, start + timedelta(days=4), subject_filter=sf)
    if period == "month":
        start = today.replace(day=1)
        return QueryIntent("homework", "month", start, today, subject_filter=sf)
    if period == "last_month":
        first = today.replace(day=1)
        end = first - timedelta(days=1)
        return QueryIntent("homework", "month", end.replace(day=1), end, subject_filter=sf)
    if period in ("trimester_1", "trimester_2", "trimester_3"):
        num = int(period[-1])
        _, start, end = TRIMESTERS[num - 1]
        return QueryIntent(
            "homework",
            "trimester",
            start,
            end,
            trimester_num=num,
            subject_filter=sf,
        )
    if period == "year":
        start = TRIMESTERS[0][1]
        end = TRIMESTERS[-1][2]
        return QueryIntent("homework", "year", start, end, subject_filter=sf)
    if period.startswith("month:"):
        try:
            month_num = int(period.split(":")[1])
            year = today.year if month_num <= today.month else today.year - 1
            start = date(year, month_num, 1)
            if month_num == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month_num + 1, 1) - timedelta(days=1)
            return QueryIntent("homework", "month", start, end, subject_filter=sf)
        except (ValueError, IndexError):
            pass
    if period.lower().strip() in _DAY_NAMES:
        d = _parse_date(period)
        return QueryIntent("homework", "day", d, d, subject_filter=sf)
    try:
        d = date.fromisoformat(period)
        return QueryIntent("homework", "day", d, d, subject_filter=sf)
    except ValueError:
        pass
    num, start, end = get_current_trimester()
    return QueryIntent("homework", "trimester", start, end, trimester_num=num, subject_filter=sf)


async def _handle_query(
    update, user_id: int, result: ExtractionResult, data: QueryExtract
) -> None:
    from schoolai.bot.query_handler import _run_query
    from schoolai.skills.query.formatter import format_homework_multi
    from schoolai.skills.query.resolver import resolve_homework_multi

    if not data.courses:
        store_pending(user_id, result)
        async with get_db_session() as session:
            grades = (
                (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
            )
        await update.message.reply_text(
            "¿De qué curso quieres la consulta?",
            reply_markup=grade_keyboard(
                grades,
                "act_grade",
                with_all_mine=(data.query_type in ("attendance", "homework")),
            ),
        )
        return

    intent = _build_query_intent(data.period, data.subject)
    intent.type = data.query_type

    grade_ids = [course_abbrev_map[c] for c in data.courses if c in course_abbrev_map]
    if not grade_ids:
        await update.message.reply_text(
            f"No reconocí los cursos: {', '.join(data.courses)}",
            parse_mode="Markdown",
        )
        return

    label = " y ".join(
        data.courses[i].upper()
        for i in range(len(data.courses))
        if data.courses[i] in course_abbrev_map
    )

    if len(grade_ids) == 1:
        await _run_query(update.message.reply_text, user_id, intent, grade_ids[0])
    elif data.query_type == "attendance":
        from schoolai.skills.query.formatter import format_attendance_multi
        from schoolai.skills.query.resolver import resolve_attendance_multi

        async with get_db_session() as session:
            data_list = await resolve_attendance_multi(intent, grade_ids, session)
        text = format_attendance_multi(data_list, label)
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        from schoolai.db.models.teacher import Teacher as _Teacher

        async with get_db_session() as session:
            teacher_subject_ids = None
            _teacher = (
                await session.execute(
                    select(_Teacher).where(_Teacher.telegram_id == user_id),
                )
            ).scalar_one_or_none()
            teacher_id_val = None
            if _teacher:
                teacher_id_val = _teacher.id
                ids = await get_teacher_subject_ids(session, _teacher.id)
                if ids:
                    teacher_subject_ids = ids
            data_list = await resolve_homework_multi(
                intent, grade_ids, session, teacher_subject_ids, teacher_id=teacher_id_val
            )
        text = format_homework_multi(data_list, label)
        await update.message.reply_text(text, parse_mode="HTML")


async def _query_my_courses_attendance(reply_fn, user_id: int, intent) -> None:
    """Consulta asistencia de todos los cursos del docente, agrupada por curso."""
    from sqlalchemy import select as _sel

    from schoolai.db.models.teacher import Schedule, Teacher
    from schoolai.skills.query.formatter import format_attendance_multi
    from schoolai.skills.query.resolver import resolve_attendance_multi

    async with get_db_session() as session:
        teacher = (
            await session.execute(_sel(Teacher).where(Teacher.telegram_id == user_id))
        ).scalar_one_or_none()

        if not teacher:
            await reply_fn("No tienes un perfil de docente registrado.")
            return

        schedule_rows = (
            (
                await session.execute(
                    _sel(Schedule)
                    .where(Schedule.teacher_id == teacher.id, Schedule.is_active.is_(True))
                    .order_by(Schedule.grade_id)
                )
            )
            .scalars()
            .all()
        )

        grade_ids = list({s.grade_id for s in schedule_rows})
        if not grade_ids:
            await reply_fn("No tienes cursos asignados en el horario.")
            return

        grade_ids_ordered = sorted(grade_ids)
        data_list = await resolve_attendance_multi(intent, grade_ids_ordered, session)

    text = format_attendance_multi(data_list, "Mis cursos")
    await reply_fn(text, parse_mode="Markdown")


async def _query_my_courses_homework(reply_fn, user_id: int, data) -> None:
    """Consulta tareas de todos los cursos del docente."""
    from sqlalchemy import select as _sel

    from schoolai.db.models.teacher import Schedule, Teacher
    from schoolai.skills.homework.repository import get_teacher_subject_ids
    from schoolai.skills.query.formatter import format_homework_multi
    from schoolai.skills.query.resolver import resolve_homework_multi

    async with get_db_session() as session:
        teacher = (
            await session.execute(_sel(Teacher).where(Teacher.telegram_id == user_id))
        ).scalar_one_or_none()

        if not teacher:
            await reply_fn("No tienes un perfil de docente registrado.")
            return

        schedule_rows = (
            (
                await session.execute(
                    _sel(Schedule)
                    .where(Schedule.teacher_id == teacher.id, Schedule.is_active.is_(True))
                    .order_by(Schedule.grade_id)
                )
            )
            .scalars()
            .all()
        )

        grade_ids = sorted({s.grade_id for s in schedule_rows})
        if not grade_ids:
            await reply_fn("No tienes cursos asignados en el horario.")
            return

        intent = _build_query_intent(data.period, data.subject)
        subject_ids = await get_teacher_subject_ids(session, teacher.id)
        data_list = await resolve_homework_multi(
            intent,
            grade_ids,
            session,
            teacher_subject_ids=subject_ids,
            teacher_id=teacher.id,
        )

    text = format_homework_multi(data_list, "Mis cursos")
    from telegram.constants import ParseMode as _PM

    await reply_fn(text, parse_mode=_PM.HTML)
