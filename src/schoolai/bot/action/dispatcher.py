"""Punto de entrada principal del pipeline de acción."""

from __future__ import annotations

from schoolai.bot.action.attendance import _handle_attendance
from schoolai.bot.action.homework import _handle_homework
from schoolai.bot.action.homework_report import _handle_homework_report
from schoolai.bot.action.query import _handle_query
from schoolai.skills.utils.schema import ExtractionResult


async def handle_extraction(update, user_id: int, result: ExtractionResult) -> None:
    """Punto de entrada principal. Actúa según el resultado del extractor."""
    intent = result.intent
    data = result.data

    if intent == "attendance":
        await _handle_attendance(update, user_id, result, data)
    elif intent == "homework":
        await _handle_homework(update, user_id, result, data)
    elif intent == "homework_report":
        await _handle_homework_report(update, user_id, result, data)
    elif intent == "query":
        await _handle_query(update, user_id, result, data)
    else:
        pass  # chat — manejado por el caller
