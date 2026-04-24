"""Tools de asistencia: record y query."""

from __future__ import annotations

from sqlalchemy import select

from schoolai.db.connection import get_db_session
from schoolai.db.models.teacher import Teacher
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.attendance.service import infer_period_from_schedule, save_absences
from schoolai.skills.homework.repository import find_grade
from schoolai.skills.orchestrator._tools.helpers import _parse_date, _period_to_dates, _strip_tags
from schoolai.skills.query.formatter import format_attendance
from schoolai.skills.query.resolver import resolve_attendance


async def _record_attendance(
    telegram_id: int,
    names: list[str],
    course: str,
    date: str = "today",
    status: str = "absent",
) -> str:
    """Records absences, tardiness or justified absences for students in a course."""
    status_map = {"absent": "F", "late": "AT", "justified": "J"}

    if status == "all_present" or not names:
        return f"Todos presentes en {course} — {_parse_date(date).strftime('%d/%m/%Y')}"

    db_status = status_map.get(status, "F")
    att_date = _parse_date(date)

    async with get_db_session() as session:
        grade = await find_grade(session, course)
        if not grade:
            return f"Curso '{course}' no encontrado."

        extracted = [{"name": n, "status": db_status} for n in names]
        matches = await match_names(extracted, grade.id, session)

        resolved = [m for m in matches if m.resolved]
        not_found = [m for m in matches if m.not_found]
        ambiguous = [m for m in matches if m.ambiguous]

        if not resolved:
            return f"No se encontraron estudiantes: {', '.join(names)}"

        _subject_name, _period_start, _period_end = None, None, None
        _teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if _teacher:
            _subject_name, _period_start, _period_end = await infer_period_from_schedule(
                session, _teacher.id, grade.id
            )

        student_ids = [m.matched_id for m in resolved]
        statuses = {m.matched_id: m.status for m in resolved}
        await save_absences(
            student_ids,
            statuses,
            att_date,
            session,
            subject_name=_subject_name,
            period_start=_period_start,
            period_end=_period_end,
        )

    labels = {"F": "Falta", "AT": "Atraso", "J": "Justificado"}
    label = labels.get(db_status, db_status)
    lines = [f"Asistencia registrada — {grade.name} — {att_date.strftime('%d/%m/%Y')}"]
    lines.extend(f"  {m.matched_name}: {label}" for m in resolved)
    if not_found:
        lines.append(f"No encontrados: {', '.join(m.raw_name for m in not_found)}")
    if ambiguous:
        names_str = ", ".join(m.raw_name for m in ambiguous)
        lines.append(f"Ambiguos (requieren apellido completo): {names_str}")
    return "\n".join(lines)


async def _query_attendance(
    courses: list[str],
    period: str = "today",
) -> str:
    """Queries the attendance record for one or more courses."""
    intent = _period_to_dates(period, "attendance")
    results = []

    async with get_db_session() as session:
        for course in courses:
            grade = await find_grade(session, course)
            if not grade:
                results.append(f"Curso '{course}' no encontrado.")
                continue
            data = await resolve_attendance(intent, grade.id, session)
            results.append(_strip_tags(format_attendance(data)))

    return "\n\n".join(results) if results else "Sin datos."
