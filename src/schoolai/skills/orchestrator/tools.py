"""Unified tools for OrchestratorSkill.

Each tool is an async function that:
  - manages its own DB session
  - returns plain text for LLM consumption (no HTML)
  - is available via tool calling (OpenAI-compatible format)

Inspired by the NanoBot pattern (HKUDS/nanobot): self-contained tools.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select

from schoolai.config import settings
from schoolai.constants import TRUNCATE_DESCRIPTION
from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.db.models.teacher import Schedule, Teacher
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.attendance.service import infer_period_from_schedule, save_absences
from schoolai.skills.context.tools import (
    delete_context_doc,
    list_context_docs,
    save_web_page,
    search_context,
    web_search,
)
from schoolai.skills.cuotas.service import (
    create_actividad,
    get_actividad_by_nombre,
    get_actividades,
    get_estado_actividad,
    get_students_in_grade,
    register_pago,
)
from schoolai.skills.cuotas.tools import ToolDef
from schoolai.skills.homework.repository import (
    delete_homework,
    find_grade,
    find_homework_by_ref,
    find_subject,
    get_teacher_subject_ids,
    save_homework,
)
from schoolai.skills.orchestrator.repl import run_repl
from schoolai.skills.query.detector import QueryIntent, get_current_trimester
from schoolai.skills.query.formatter import format_attendance, format_homework_multi
from schoolai.skills.query.resolver import resolve_attendance, resolve_homework
from schoolai.skills.reminders.tools import cancel_reminder, create_reminder, list_reminders

# ── Helpers ───────────────────────────────────────────────────────────────────


def _strip_tags(text: str) -> str:
    """Remove HTML tags so the LLM receives clean text."""
    return re.sub(r"<[^>]+>", "", text)


def _today() -> date:
    """Return today's date in the school's timezone."""
    tz = ZoneInfo(settings.school_timezone) if settings.school_timezone else None
    return datetime.now(tz).date()


def _parse_date(value: str) -> date:
    today = _today()
    if value in ("today", "hoy"):
        return today
    if value in ("yesterday", "ayer"):
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(value)
    except ValueError:
        logger.warning(f"[tools] fecha inválida: {value!r}, usando hoy")
        return today


def _period_to_dates(period: str, qtype: str):
    """Convert a period string to a QueryIntent."""
    today = _today()
    p = period.lower().strip()

    if p in ("today", "hoy"):
        return QueryIntent(qtype, "day", today, today)
    if p in ("yesterday", "ayer"):
        d = today - timedelta(days=1)
        return QueryIntent(qtype, "day", d, d)
    if p in ("week", "semana", "esta_semana"):
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=4)
        return QueryIntent(qtype, "week", start, end)
    if p in ("month", "mes", "este_mes"):
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(day=31)
        else:
            end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
        return QueryIntent(qtype, "month", start, end)
    # Default: current trimester
    num, start, end = get_current_trimester()
    return QueryIntent(qtype, "trimester", start, end, trimester_num=num)


# ── Implementations ───────────────────────────────────────────────────────────


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

    async with async_session() as session:
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

        # Infer current period from teacher's schedule
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

    async with async_session() as session:
        for course in courses:
            grade = await find_grade(session, course)
            if not grade:
                results.append(f"Curso '{course}' no encontrado.")
                continue
            data = await resolve_attendance(intent, grade.id, session)
            results.append(_strip_tags(format_attendance(data)))

    return "\n\n".join(results) if results else "Sin datos."


async def _create_assignment(
    telegram_id: int,
    description: str,
    course: str,
    subjects: list[str] | None = None,
    due_date: str | None = None,
) -> str:
    """Records a new homework assignment for a course.

    If multiple subjects are specified, creates one record per subject,
    each with its own sequence_num within that subject.
    Only subjects assigned to the teacher in their schedule are allowed.
    """
    subjects = [s for s in (subjects or []) if s]
    delivery = _parse_date(due_date) if due_date else None

    async with async_session() as session:
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
    """Queries recorded homework assignments for one or more courses.

    Only shows assignments for subjects the teacher is scheduled to teach.
    """
    intent = _period_to_dates(period, "homework")
    hw_data = []
    not_found = []

    async with async_session() as session:
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
    """Deletes a homework assignment by sequence number and course. Submissions cascade."""
    async with async_session() as session:
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


async def _list_courses(level: str | None = None) -> str:
    """Lists available courses, optionally filtered by education level."""
    level_aliases = {
        "basica": "egb",
        "básica": "egb",
        "general": "egb",
        "educacion": "egb",
        "educación": "egb",
    }

    async with async_session() as session:
        stmt = select(Grade).order_by(Grade.sort_order)
        grades = (await session.execute(stmt)).scalars().all()

    if level:
        db_level = level_aliases.get(level.lower(), level.lower())
        grades = [g for g in grades if (g.level or "").lower() == db_level]

    if not grades:
        suffix = f" de nivel '{level}'" if level else ""
        return f"No se encontraron cursos{suffix}."

    lines = [f"Cursos disponibles{f' ({level})' if level else ''}:"]
    lines.extend(f"  {g.name}" for g in grades)
    return "\n".join(lines)


async def _list_activities(telegram_id: int) -> str:
    """Lists active school activities filtered by the requesting teacher."""
    async with async_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not teacher:
            return "No se encontró tu registro de docente."
        actividades = await get_actividades(session, teacher_id=teacher.id, only_active=True)

    if not actividades:
        return "No hay actividades activas."

    lines = ["Actividades activas:"]
    lines.extend(f"  [{a.id}] {a.nombre} — ${a.monto:.2f}" for a in actividades)
    return "\n".join(lines)


async def _create_activity(
    name: str,
    amount: float,
    course: str | None = None,
) -> str:
    """Creates a new school activity or fee."""
    async with async_session() as session:
        actividad = await create_actividad(session, name, amount)
        act_id = actividad.id

        lines = [f"Actividad creada: '{name}' — ${amount:.2f} (ID: {act_id})"]

        if course:
            grade = await find_grade(session, course)
            if grade:
                students = await get_students_in_grade(session, grade.id)
                count = await add_participantes(session, act_id, [s.id for s in students])
                lines.append(
                    f"  {count} estudiantes de {grade.name} agregados como participantes.",
                )
            else:
                lines.append(
                    f"  Curso '{course}' no encontrado — participantes no agregados.",
                )

    return "\n".join(lines)


async def _activity_status(name: str) -> str:
    """Queries the payment status of an activity by name."""
    async with async_session() as session:
        actividad = await get_actividad_by_nombre(session, name)
        if not actividad:
            return f"Actividad '{name}' no encontrada."
        act, participantes = await get_estado_actividad(session, actividad.id)

    if not act:
        return f"Actividad '{name}' no encontrada."

    total = len(participantes)
    paid = sum(1 for p in participantes if p.is_complete)
    pending = total - paid

    lines = [
        f"Actividad: {act.nombre} — ${act.monto:.2f}",
        f"  Pagaron completo: {paid}/{total}",
        f"  Pendientes: {pending}",
    ]
    if participantes:
        lines.append("  Detalle:")
        for p in participantes:
            icon = "✓" if p.is_complete else "·"
            pagado = float(p.total_pagado or 0)
            lines.append(f"    {icon} Estudiante #{p.student_id}: ${pagado:.2f}")
    return "\n".join(lines)


async def _register_payment(
    names: list[str],
    amount: float,
    activity: str,
    course: str | None = None,
) -> str:
    """Records a payment from one or more students for an activity."""
    if not course:
        return "Se requiere el curso para identificar a los estudiantes."

    async with async_session() as session:
        act = await get_actividad_by_nombre(session, activity)
        if not act:
            return f"Actividad '{activity}' no encontrada."

        grade = await find_grade(session, course)
        if not grade:
            return f"Curso '{course}' no encontrado."

        extracted = [{"name": n, "status": "F"} for n in names]
        matches = await match_names(extracted, grade.id, session)
        resolved = [m for m in matches if m.resolved]

        if not resolved:
            return f"No se encontraron estudiantes: {', '.join(names)}"

        registered = []
        for m in resolved:
            await register_pago(session, act.id, m.matched_id, amount)
            registered.append(m.matched_name)

    lines = [f"Pagos registrados — {act.nombre} — ${amount:.2f} c/u:"]
    lines.extend(f"  ✓ {n}" for n in registered)
    not_found = [m.raw_name for m in matches if not m.resolved]
    if not_found:
        lines.append(f"No encontrados: {', '.join(not_found)}")
    return "\n".join(lines)


# ── Teacher context ────────────────────────────────────────────────────────────


async def _my_courses(telegram_id: int) -> str:
    """Returns the current teacher's assigned courses and subjects."""
    async with async_session() as session:
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


async def _my_schedule(telegram_id: int, day: str | None = None) -> str:
    """Returns the teacher's weekly schedule, optionally filtered by day."""
    async with async_session() as session:
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


# ── Python REPL ───────────────────────────────────────────────────────────────


async def _python_repl(code: str) -> str:
    """Executes restricted Python code with read-only DB access."""
    return await run_repl(code)


# ── Context documents ─────────────────────────────────────────────────────────


async def _search_context(
    telegram_id: int,
    query: str,
    category: str | None = None,
) -> str:
    """Searches the teacher's context documents (personal + institutional)."""
    return await search_context(telegram_id=telegram_id, query=query, category=category)


async def _list_context_docs(
    telegram_id: int,
    category: str | None = None,
    scope: str | None = None,
) -> str:
    """Lists available context documents for the teacher."""
    return await list_context_docs(telegram_id=telegram_id, category=category, scope=scope)


async def _delete_context_doc(telegram_id: int, doc_id: int) -> str:
    """Deletes a context document by ID."""
    return await delete_context_doc(telegram_id=telegram_id, doc_id=doc_id)


async def _web_search(query: str) -> str:
    """Searches the internet via DuckDuckGo and returns top results."""
    return await web_search(query=query)


async def _save_web_page(telegram_id: int, url: str, hint: str | None = None) -> str:
    """Downloads a web page and saves it as a context document."""
    return await save_web_page(telegram_id=telegram_id, url=url, hint=hint)


# ── Reminders ─────────────────────────────────────────────────────────────────


async def _create_reminder(
    telegram_id: int,
    message: str,
    scheduled_at: str,
    target: str = "teacher",
    course: str | None = None,
) -> str:
    """Schedules a reminder via Telegram (teacher) and/or WhatsApp (parents)."""
    return await create_reminder(
        telegram_id=telegram_id,
        message=message,
        scheduled_at=scheduled_at,
        target=target,
        course=course,
    )


async def _list_reminders(telegram_id: int, status: str = "pending") -> str:
    """Lists the teacher's reminders."""
    return await list_reminders(telegram_id=telegram_id, status=status)


async def _cancel_reminder(telegram_id: int, reminder_id: int) -> str:
    """Cancels a pending reminder by ID."""
    return await cancel_reminder(telegram_id=telegram_id, reminder_id=reminder_id)


# ── Registry ──────────────────────────────────────────────────────────────────


TOOLS: list[ToolDef] = [
    ToolDef(
        name="record_attendance",
        description=(
            "Records absences, tardiness, or justified absences for students in a course. "
            "Use status='all_present' if all students attended."
        ),
        parameters={
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Last names or first names of the absent/late students",
                },
                "course": {
                    "type": "string",
                    "description": "Course abbreviation, e.g.: 3bt, 8egb, prep",
                },
                "date": {
                    "type": "string",
                    "description": "today, yesterday, or YYYY-MM-DD. Default: today",
                },
                "status": {
                    "type": "string",
                    "enum": ["absent", "late", "justified", "all_present"],
                    "description": (
                        "absent=missed class, late=tardy, "
                        "justified=excused absence, all_present=everyone attended"
                    ),
                },
                "telegram_id": {
                    "type": "integer",
                    "description": "Telegram ID of the teacher making the record (injected automatically)",
                },
            },
            "required": ["names", "course", "telegram_id"],
        },
        fn=_record_attendance,
    ),
    ToolDef(
        name="query_attendance",
        description="Queries the attendance record for one or more courses.",
        parameters={
            "type": "object",
            "properties": {
                "courses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Course abbreviations, e.g.: ['3bt', '8egb']",
                },
                "period": {
                    "type": "string",
                    "description": "today, yesterday, week, month, trimestre. Default: today",
                },
            },
            "required": ["courses"],
        },
        fn=_query_attendance,
    ),
    ToolDef(
        name="create_assignment",
        description=(
            "Records a new homework assignment, task, or activity for a course. "
            "Only subjects in the teacher's own schedule are allowed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "Teacher's Telegram ID (use exactly the value from the system prompt)",
                },
                "description": {
                    "type": "string",
                    "description": "Full description of the homework or assignment",
                },
                "course": {"type": "string", "description": "Course abbreviation, e.g.: 3bt"},
                "subjects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of subjects. If the teacher names several subjects separated "
                        "by '/' or ',', split them into individual items. "
                        "Use the full subject name as the teacher wrote it. Optional."
                    ),
                },
                "due_date": {
                    "type": "string",
                    "description": "Due date YYYY-MM-DD. Optional.",
                },
            },
            "required": ["telegram_id", "description", "course"],
        },
        fn=_create_assignment,
    ),
    ToolDef(
        name="query_assignments",
        description=(
            "Queries the recorded homework assignments for one or more courses. "
            "Only shows assignments for the teacher's own subjects."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "Teacher's Telegram ID (use exactly the value from the system prompt)",
                },
                "courses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Course abbreviations",
                },
                "period": {
                    "type": "string",
                    "description": "today, yesterday, week, month, trimestre. Default: trimestre",
                },
            },
            "required": ["telegram_id", "courses"],
        },
        fn=_query_assignments,
    ),
    ToolDef(
        name="delete_assignment",
        description=(
            "Permanently deletes a homework assignment by its sequence number and course. "
            "Only call this after the teacher has explicitly confirmed the deletion."
        ),
        parameters={
            "type": "object",
            "properties": {
                "number": {
                    "type": "integer",
                    "description": "Homework sequence number shown in the list, e.g.: 2",
                },
                "course": {
                    "type": "string",
                    "description": "Course abbreviation, e.g.: 1bt",
                },
            },
            "required": ["number", "course"],
        },
        fn=_delete_assignment,
    ),
    ToolDef(
        name="list_courses",
        description=(
            "Lists all available courses with their abbreviations. "
            "Call this BEFORE query_attendance or query_assignments when the teacher "
            "mentions a generic level (bachillerato, egb, básica, inicial) without giving "
            "the exact course code."
        ),
        parameters={
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "enum": ["bachillerato", "egb", "inicial"],
                    "description": (
                        "Education level to filter: 'bachillerato', 'egb' (basic), 'inicial'. "
                        "Omit to list all courses."
                    ),
                },
            },
            "required": [],
        },
        fn=_list_courses,
    ),
    ToolDef(
        name="list_activities",
        description="Lists active school activities and fees (cuotas) for the current teacher.",
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "Telegram ID of the teacher (injected automatically)",
                },
            },
            "required": ["telegram_id"],
        },
        fn=_list_activities,
    ),
    ToolDef(
        name="create_activity",
        description="Creates a new school activity or fee with a name and amount.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Activity name"},
                "amount": {"type": "number", "description": "Amount in dollars"},
                "course": {
                    "type": "string",
                    "description": (
                        "Course abbreviation to auto-enroll students as participants. Optional."
                    ),
                },
            },
            "required": ["name", "amount"],
        },
        fn=_create_activity,
    ),
    ToolDef(
        name="activity_status",
        description="Queries the payment status of an activity by name.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Activity name"},
            },
            "required": ["name"],
        },
        fn=_activity_status,
    ),
    ToolDef(
        name="register_payment",
        description="Records a payment from one or more students for an activity.",
        parameters={
            "type": "object",
            "properties": {
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Last names of the students who paid",
                },
                "amount": {"type": "number", "description": "Amount paid in dollars"},
                "activity": {"type": "string", "description": "Activity name"},
                "course": {"type": "string", "description": "Course abbreviation"},
            },
            "required": ["names", "amount", "activity", "course"],
        },
        fn=_register_payment,
    ),
    ToolDef(
        name="my_courses",
        description=(
            "Returns the current teacher's assigned courses and subjects. "
            "Call this when the teacher asks about their own courses, subjects, or grades. "
            "Pass the teacher's Telegram ID exactly as given in the system prompt."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
            },
            "required": ["telegram_id"],
        },
        fn=_my_courses,
    ),
    ToolDef(
        name="my_schedule",
        description=(
            "Returns the current teacher's weekly schedule, optionally filtered by day. "
            "Call this when the teacher asks about their schedule or timetable. "
            "Pass the teacher's Telegram ID exactly as given in the system prompt."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "day": {
                    "type": "string",
                    "description": (
                        "Day filter in Spanish or English: lunes, martes, miércoles, "
                        "jueves, viernes. Omit for full week."
                    ),
                },
            },
            "required": ["telegram_id"],
        },
        fn=_my_schedule,
    ),
    ToolDef(
        name="python_repl",
        description=(
            "Executes Python code with read-only PostgreSQL access. "
            "Use for custom queries not covered by other tools.\n"
            "\n"
            "ONLY these are available inside the code:\n"
            "  await query(sql, params={}) → list[dict]   # runs SELECT/WITH\n"
            "  today  → date    now → datetime    print(...) → output\n"
            "  Imports allowed: datetime, math, collections, re, json, decimal\n"
            "DO NOT use default_api, os, sys, open, or any other tool name.\n"
            "\n"
            "DB schema (PostgreSQL — status values are strings with quotes in SQL):\n"
            "  people(id, first_name, last_name, second_last_name)\n"
            "  students(id, person_id, grade_id, section, status)  -- status='active'|'inactive'\n"
            "  grades(id, name, level, sort_order)\n"
            "  subjects(id, name, area)\n"
            "  attendance(id, student_id, date DATE, status)  -- status='F' 'AT' 'J'\n"
            "  homework(id, grade_id, subject_id, trimester_num, sequence_num, homework TEXT, is_open BOOL)\n"
            "  actividades(id, nombre, monto, is_active)\n"
            "  actividad_participantes(id, actividad_id, student_id, total_pagado, is_complete)\n"
            "\n"
            "SQL RULES (PostgreSQL):\n"
            "  - Dates: use >= and < operators, NOT LIKE. Ex: date >= '2026-03-01' AND date < '2026-04-01'\n"
            "  - String values always in single quotes: status = 'F', status = 'active'\n"
            "  - Always print results; do not just assign them.\n"
            "\n"
            "EXAMPLE:\n"
            "  rows = await query(\"SELECT COUNT(*) as n FROM students WHERE status = 'active'\")\n"
            "  print(rows[0]['n'])"
        ),
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code. Use await query(sql) and print() for output.",
                },
            },
            "required": ["code"],
        },
        fn=_python_repl,
    ),
    ToolDef(
        name="search_context",
        description=(
            "Searches the teacher's context documents (personal and institutional) "
            "using full-text search. Call this when answering questions that may require "
            "information the teacher previously uploaded (schedule, school calendar, policies, etc.)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "query": {
                    "type": "string",
                    "description": "The search query in Spanish.",
                },
                "category": {
                    "type": "string",
                    "enum": ["schedule", "calendar", "policies", "contacts", "notes", "other"],
                    "description": "Optional category filter.",
                },
            },
            "required": ["telegram_id", "query"],
        },
        fn=_search_context,
    ),
    ToolDef(
        name="list_context_docs",
        description="Lists the context documents available to the teacher.",
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "category": {
                    "type": "string",
                    "enum": ["schedule", "calendar", "policies", "contacts", "notes", "other"],
                    "description": "Optional category filter.",
                },
                "scope": {
                    "type": "string",
                    "enum": ["personal", "institution"],
                    "description": "Optional scope filter.",
                },
            },
            "required": ["telegram_id"],
        },
        fn=_list_context_docs,
    ),
    ToolDef(
        name="delete_context_doc",
        description="Deletes a context document by its ID. Ask for confirmation before calling.",
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "doc_id": {
                    "type": "integer",
                    "description": "The document ID to delete.",
                },
            },
            "required": ["telegram_id", "doc_id"],
        },
        fn=_delete_context_doc,
    ),
    ToolDef(
        name="web_search",
        description=(
            "Searches the internet via DuckDuckGo. Use when the teacher asks about something "
            "not found in their context documents (regulations, school calendars, general info). "
            "Returns title, snippet and URL for each result. "
            "After showing results, offer to save a relevant URL with save_web_page."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query in the most specific form possible.",
                },
            },
            "required": ["query"],
        },
        fn=_web_search,
    ),
    ToolDef(
        name="save_web_page",
        description=(
            "Downloads a web page or online document and saves it as a context document "
            "for future queries. Use after web_search when the teacher confirms they want "
            "to save a result."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "url": {
                    "type": "string",
                    "description": "The URL to download and save.",
                },
                "hint": {
                    "type": "string",
                    "description": "Optional description to help categorize the document.",
                },
            },
            "required": ["telegram_id", "url"],
        },
        fn=_save_web_page,
    ),
    ToolDef(
        name="create_reminder",
        description=(
            "Schedules a new reminder for the teacher (Telegram) and/or course parents (WhatsApp). "
            "target: 'teacher' | 'parents' | 'both'. "
            "course is required when target is 'parents' or 'both'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "message": {
                    "type": "string",
                    "description": "The reminder text to send.",
                },
                "scheduled_at": {
                    "type": "string",
                    "description": "ISO 8601 datetime, e.g. 2026-04-04T07:00:00",
                },
                "target": {
                    "type": "string",
                    "enum": ["teacher", "parents", "both"],
                    "description": (
                        "teacher=Telegram to teacher, parents=WhatsApp to course parents, "
                        "both=both channels."
                    ),
                },
                "course": {
                    "type": "string",
                    "description": "Course abbreviation. Required when target is 'parents' or 'both'.",
                },
            },
            "required": ["telegram_id", "message", "scheduled_at", "target"],
        },
        fn=_create_reminder,
    ),
    ToolDef(
        name="list_reminders",
        description="Lists the teacher's reminders filtered by status.",
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "sent", "failed", "cancelled", "all"],
                    "description": "Filter by status. Default: 'pending'.",
                },
            },
            "required": ["telegram_id"],
        },
        fn=_list_reminders,
    ),
    ToolDef(
        name="cancel_reminder",
        description="Cancels a pending reminder by its ID.",
        parameters={
            "type": "object",
            "properties": {
                "telegram_id": {
                    "type": "integer",
                    "description": "The teacher's Telegram ID from the system prompt.",
                },
                "reminder_id": {
                    "type": "integer",
                    "description": "The reminder ID to cancel.",
                },
            },
            "required": ["telegram_id", "reminder_id"],
        },
        fn=_cancel_reminder,
    ),
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


async def execute_tool(name: str, args: dict) -> str:
    """Executes a tool by name. Returns string for the LLM."""
    tool = TOOLS_BY_NAME.get(name)
    if not tool or tool.fn is None:
        return f"Tool '{name}' not found."
    try:
        result = await tool.fn(**args)
        return str(result)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[orchestrator] tool={name} error: {e}")
        return f"Error in '{name}': {e}"
