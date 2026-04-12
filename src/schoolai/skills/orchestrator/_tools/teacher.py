"""Tools de contexto del docente: my_courses y my_schedule."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from schoolai.db.connection import get_db_session
from schoolai.db.models.teacher import Schedule, Teacher

_DAYS_MAP = {
    "lunes": 0,
    "martes": 1,
    "miércoles": 2,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
}
_DAYS_NAME = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


async def _my_courses(telegram_id: int) -> str:
    """Returns the current teacher's assigned courses and subjects."""
    async with get_db_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not teacher:
            return "No se encontró tu perfil de docente en el sistema."

        schedules = (
            (
                await session.execute(
                    select(Schedule).where(
                        Schedule.teacher_id == teacher.id,
                        Schedule.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )

    if not schedules:
        return "No tienes cursos asignados en el horario."

    by_grade: dict[str, set[str]] = defaultdict(set)
    for s in schedules:
        by_grade[s.grade.name].add(s.subject.name)

    person = teacher.person
    teacher_name = f"{person.first_name} {person.last_name}"
    lines = [f"Cursos y materias de {teacher_name}:"]
    for grade in sorted(by_grade):
        subj = ", ".join(sorted(by_grade[grade]))
        lines.append(f"  <b>{grade}</b>: {subj}")
    return "\n".join(lines)


async def _my_schedule(telegram_id: int, day: str | None = None) -> str:
    """Returns the teacher's weekly schedule, optionally filtered by day."""
    async with get_db_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not teacher:
            return "No se encontró tu perfil de docente en el sistema."

        stmt = (
            select(Schedule)
            .where(
                Schedule.teacher_id == teacher.id,
                Schedule.is_active.is_(True),
            )
            .order_by(Schedule.day_of_week, Schedule.period_num)
        )

        if day:
            day_num = _DAYS_MAP.get(day.lower().strip())
            if day_num is not None:
                stmt = stmt.where(Schedule.day_of_week == day_num)

        schedules = (await session.execute(stmt)).scalars().all()

    if not schedules:
        suffix = f" el {day}" if day else ""
        return f"No tienes clases registradas{suffix}."

    by_day: dict[int, list[str]] = defaultdict(list)
    for s in schedules:
        by_day[s.day_of_week].append(
            f"    P{s.period_num} {s.start_time}-{s.end_time}: "
            f"<b>{s.grade.name}</b> — {s.subject.name}"
        )

    lines = ["Tu horario:"]
    for day_num in sorted(by_day):
        lines.append(f"  <b>{_DAYS_NAME[day_num]}</b>")
        lines.extend(by_day[day_num])
    return "\n".join(lines)
