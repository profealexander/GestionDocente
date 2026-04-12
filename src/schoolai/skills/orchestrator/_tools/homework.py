"""Tools de tareas: create, query, delete."""

from __future__ import annotations

from sqlalchemy import select

from schoolai.constants import TRUNCATE_DESCRIPTION
from schoolai.db.connection import get_db_session
from schoolai.db.models.teacher import Teacher
from schoolai.skills.homework.repository import (
    delete_homework,
    find_grade,
    find_homework_by_ref,
    find_subject,
    get_teacher_subject_ids,
    save_homework,
)
from schoolai.skills.orchestrator._tools.helpers import _parse_date, _period_to_dates, _strip_tags
from schoolai.skills.query.formatter import format_homework_multi
from schoolai.skills.query.resolver import resolve_homework


async def _create_assignment(
    telegram_id: int,
    description: str,
    course: str,
    subjects: list[str] | None = None,
    due_date: str | None = None,
) -> str:
    """Records a new homework assignment for a course."""
    subjects = [s for s in (subjects or []) if s]
    delivery = _parse_date(due_date) if due_date else None

    async with get_db_session() as session:
        grade = await find_grade(session, course)
        if not grade:
            return f"Curso '{course}' no encontrado."

        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        teacher_id = teacher.id if teacher else None

        allowed_ids: list[int] | None = None
        if teacher_id:
            ids = await get_teacher_subject_ids(session, teacher_id, grade.id)
            if ids:
                allowed_ids = ids

        date_str = delivery.strftime("%d/%m/%Y") if delivery else "sin fecha"

        if len(subjects) <= 1:
            subject_id, subject_name = None, None
            if subjects:
                subject = await find_subject(session, subjects[0])
                if subject and allowed_ids is not None and subject.id not in allowed_ids:
                    return (
                        f"No tienes asignada la materia '{subject.name}' en {grade.name}. "
                        "Solo puedes crear tareas para tus asignaturas."
                    )
                subject_id = subject.id if subject else None
                subject_name = subject.name if subject else subjects[0]

            hw = await save_homework(
                session,
                homework=description,
                grade_id=grade.id,
                subject_id=subject_id,
                delivery_date=delivery,
                teacher_id=teacher_id,
            )
            subject_str = f" | {subject_name}" if subject_name else ""
            return (
                f"Tarea #{hw.sequence_num} registrada — {grade.name}{subject_str} — {date_str}"
                f"\n  {description}"
            )

        lines = [f"Tareas registradas — {grade.name} — {date_str}:"]
        skipped = []
        for subject_name in subjects:
            subject = await find_subject(session, subject_name)
            if subject and allowed_ids is not None and subject.id not in allowed_ids:
                skipped.append(subject.name)
                continue
            subject_id = subject.id if subject else None
            subject_display = subject.name if subject else subject_name
            hw = await save_homework(
                session,
                homework=description,
                grade_id=grade.id,
                subject_id=subject_id,
                delivery_date=delivery,
                teacher_id=teacher_id,
            )
            lines.append(f"  #{hw.sequence_num} {subject_display}")

        if skipped:
            lines.append(f"  Omitidas (no son tus materias): {', '.join(skipped)}")
        lines.append(f"  Descripcion: {description}")
        return "\n".join(lines)


async def _query_assignments(
    telegram_id: int,
    courses: list[str],
    period: str = "trimestre",
) -> str:
    """Queries recorded homework assignments for one or more courses."""
    intent = _period_to_dates(period, "homework")
    hw_data = []
    not_found = []

    async with get_db_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        teacher_id = teacher.id if teacher else None

        for course in courses:
            grade = await find_grade(session, course)
            if not grade:
                not_found.append(course)
                continue
            teacher_subject_ids = None
            if teacher_id:
                ids = await get_teacher_subject_ids(session, teacher_id, grade.id)
                if ids:
                    teacher_subject_ids = ids
            data = await resolve_homework(intent, grade.id, session, teacher_subject_ids)
            hw_data.append(data)

    if not hw_data:
        return "Sin tareas registradas."

    text = _strip_tags(format_homework_multi(hw_data))
    if not_found:
        text += f"\nCursos no encontrados: {', '.join(not_found)}"
    return text


async def _delete_assignment(number: int, course: str) -> str:
    """Deletes a homework assignment by sequence number and course."""
    async with get_db_session() as session:
        grade = await find_grade(session, course)
        if not grade:
            return f"Curso '{course}' no encontrado."

        hw = await find_homework_by_ref(session, number, grade.id, any_trimester=True)
        if not hw:
            return f"Tarea #{number} no encontrada en {grade.name}."

        desc = hw.homework
        seq = hw.sequence_num
        await delete_homework(session, hw.id)

    return f"Tarea #{seq} eliminada — {grade.name}: {desc[:TRUNCATE_DESCRIPTION]}"
