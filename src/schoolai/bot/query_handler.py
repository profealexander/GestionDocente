"""Helpers de ejecución y formato de consultas."""

from loguru import logger
from telegram.constants import ParseMode

from schoolai.db.connection import async_session
from schoolai.skills.query.detector import QueryIntent
from schoolai.skills.query.formatter import format_attendance, format_homework
from schoolai.skills.query.resolver import resolve_attendance, resolve_homework


async def _run_query(reply_fn, user_id: int, intent: QueryIntent, grade_id: int) -> None:
    async with async_session() as session:
        if intent.type == "attendance":
            data = await resolve_attendance(intent, grade_id, session)
            text = format_attendance(data)
            mode = ParseMode.MARKDOWN
        else:
            data = await resolve_homework(intent, grade_id, session)
            text = format_homework(data)
            mode = ParseMode.HTML

    await reply_fn(text, parse_mode=mode)
    logger.info(f"[query] grade={grade_id} done")
