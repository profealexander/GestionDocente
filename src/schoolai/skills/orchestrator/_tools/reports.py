"""Tools de reportes PDF — usados por ReportsController en el Agent Runtime."""

from __future__ import annotations

from schoolai.db.connection import get_db_session
from schoolai.skills.homework.repository import find_grade
from schoolai.skills.orchestrator._tools.helpers import _parse_date
from schoolai.skills.query.detector import QueryIntent
from schoolai.skills.query.resolver import resolve_attendance, resolve_homework
from schoolai.skills.reports.attendance import generate_attendance_pdf
from schoolai.skills.reports.homework import generate_homework_pdf


async def _report_attendance_pdf(
    telegram_id: int,
    course: str,
    date_from: str = "today",
    date_to: str | None = None,
) -> bytes:
    """Generates a PDF attendance report for a course. Returns raw bytes."""
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to) if date_to else d_from

    async with get_db_session() as session:
        grade = await find_grade(session, course)
        if not grade:
            raise ValueError(f"Curso '{course}' no encontrado.")

        intent = QueryIntent(
            type="attendance",
            period="day",
            period_start=d_from,
            period_end=d_to,
        )
        data = await resolve_attendance(intent, grade.id, session)

    return generate_attendance_pdf(data)


async def _report_homework_pdf(
    telegram_id: int,
    course: str,
) -> bytes:
    """Generates a PDF homework report for a course. Returns raw bytes."""
    from datetime import date

    today = date.today()
    async with get_db_session() as session:
        grade = await find_grade(session, course)
        if not grade:
            raise ValueError(f"Curso '{course}' no encontrado.")

        intent = QueryIntent(
            type="homework",
            period="trimester",
            period_start=today.replace(month=1, day=1),
            period_end=today,
        )
        data = await resolve_homework(intent, grade.id, session)

    return generate_homework_pdf(data)
