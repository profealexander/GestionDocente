"""Helpers de ejecución y formato de consultas."""

from loguru import logger
from telegram.constants import ParseMode

from schoolai.db.connection import async_session
from schoolai.skills.query.detector import QueryIntent
from schoolai.skills.query.formatter import format_attendance, format_homework
from schoolai.skills.query.resolver import resolve_attendance, resolve_homework


async def _run_query(reply_fn, user_id: int, intent: QueryIntent, grade_id: int) -> None:
    from sqlalchemy import select

    from schoolai.bot.state import set_conversation_ctx
    from schoolai.db.models.grade import Grade
    from schoolai.db.models.teacher import Teacher
    from schoolai.skills.homework.repository import get_teacher_subject_ids

    async with async_session() as session:
        grade_name: str | None = None
        grade_obj = (
            await session.execute(select(Grade).where(Grade.id == grade_id))
        ).scalar_one_or_none()
        if grade_obj:
            grade_name = grade_obj.name

        if intent.type == "attendance":
            data = await resolve_attendance(intent, grade_id, session)
            text = format_attendance(data)
            mode = ParseMode.MARKDOWN
        else:
            teacher_subject_ids = None
            teacher = (
                await session.execute(select(Teacher).where(Teacher.telegram_id == user_id))
            ).scalar_one_or_none()
            teacher_id_val = None
            if teacher:
                teacher_id_val = teacher.id
                ids = await get_teacher_subject_ids(session, teacher.id, grade_id)
                if ids:
                    teacher_subject_ids = ids
            data = await resolve_homework(
                intent, grade_id, session, teacher_subject_ids, teacher_id=teacher_id_val
            )
            text = format_homework(data)
            mode = ParseMode.HTML

    await reply_fn(text, parse_mode=mode)
    # Guardar contexto conversacional para que "editar" sepa a qué se refiere
    set_conversation_ctx(user_id, intent.type, grade_id=grade_id, grade_name=grade_name)
    logger.info(f"[query] grade={grade_id} done")
