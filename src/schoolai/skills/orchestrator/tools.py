"""Herramientas unificadas para OrchestratorSkill.

Cada tool es una función async que:
  - maneja su propia sesión DB
  - retorna texto plano para consumo del LLM (no HTML)
  - está disponible para GLM-4.7-Flash via tool calling

Inspirado en el patrón NanoBot (HKUDS/nanobot): tools autocontenidas.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from loguru import logger

from schoolai.skills.cuotas.tools import ToolDef

# ── Helpers ───────────────────────────────────────────────────────────────────


def _strip_tags(text: str) -> str:
    """Elimina etiquetas HTML para que el LLM reciba texto limpio."""
    return re.sub(r"<[^>]+>", "", text)


def _parse_date(fecha: str) -> date:
    today = date.today()  # noqa: DTZ011
    if fecha in ("today", "hoy"):
        return today
    if fecha in ("yesterday", "ayer"):
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(fecha)
    except ValueError:
        return today


def _period_to_dates(periodo: str, qtype: str):
    """Convierte string de periodo a QueryIntent."""
    from schoolai.skills.query.detector import QueryIntent, get_current_trimester

    today = date.today()  # noqa: DTZ011
    p = periodo.lower().strip()

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
    # Default: trimestre actual
    num, start, end = get_current_trimester()
    return QueryIntent(qtype, "trimester", start, end, trimester_num=num)


# ── Implementaciones ──────────────────────────────────────────────────────────


async def _registrar_asistencia(
    nombres: list[str],
    curso: str,
    fecha: str = "today",
    status: str = "absent",
) -> str:
    """Registra asistencia (faltas/atrasos/justificados) en un curso."""
    from schoolai.db.connection import async_session
    from schoolai.skills.attendance.matcher import match_names
    from schoolai.skills.attendance.service import save_absences
    from schoolai.skills.homework.repository import find_grade

    status_map = {"absent": "F", "late": "AT", "justified": "J"}

    if status == "all_present" or not nombres:
        return f"Todos presentes en {curso} — {_parse_date(fecha).strftime('%d/%m/%Y')}"

    db_status = status_map.get(status, "F")
    att_date = _parse_date(fecha)

    async with async_session() as session:
        grade = await find_grade(session, curso)
        if not grade:
            return f"Curso '{curso}' no encontrado."

        extracted = [{"name": n, "status": db_status} for n in nombres]
        matches = await match_names(extracted, grade.id, session)

        resolved = [m for m in matches if m.resolved]
        not_found = [m for m in matches if m.not_found]
        ambiguous = [m for m in matches if m.ambiguous]

        if not resolved:
            return f"No se encontraron estudiantes: {', '.join(nombres)}"

        student_ids = [m.matched_id for m in resolved]
        statuses = {m.matched_id: m.status for m in resolved}
        await save_absences(student_ids, statuses, att_date, session)

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


async def _consultar_asistencia(
    cursos: list[str],
    periodo: str = "today",
) -> str:
    """Consulta el registro de asistencia de uno o varios cursos."""
    from schoolai.db.connection import async_session
    from schoolai.skills.homework.repository import find_grade
    from schoolai.skills.query.formatter import format_attendance
    from schoolai.skills.query.resolver import resolve_attendance

    intent = _period_to_dates(periodo, "attendance")
    results = []

    async with async_session() as session:
        for curso in cursos:
            grade = await find_grade(session, curso)
            if not grade:
                results.append(f"Curso '{curso}' no encontrado.")
                continue
            data = await resolve_attendance(intent, grade.id, session)
            results.append(_strip_tags(format_attendance(data)))

    return "\n\n".join(results) if results else "Sin datos."


async def _crear_tarea(
    descripcion: str,
    curso: str,
    materias: list[str] | None = None,
    fecha_entrega: str | None = None,
) -> str:
    """Registra una nueva tarea para un curso.

    Si se especifican múltiples materias, crea un registro independiente por cada
    una (una tarea por materia). Cada registro tiene su propio sequence_num dentro
    de su materia, permitiendo referenciarla individualmente.
    """
    from schoolai.db.connection import async_session
    from schoolai.skills.homework.repository import find_grade, find_subject, save_homework

    materias = [m for m in (materias or []) if m]
    delivery = _parse_date(fecha_entrega) if fecha_entrega else None

    async with async_session() as session:
        grade = await find_grade(session, curso)
        if not grade:
            return f"Curso '{curso}' no encontrado."

        date_str = delivery.strftime("%d/%m/%Y") if delivery else "sin fecha"

        if len(materias) <= 1:
            # Sin materia o una sola — un registro
            subject_id, subject_name = None, None
            if materias:
                subject = await find_subject(session, materias[0])
                subject_id = subject.id if subject else None
                subject_name = subject.name if subject else materias[0]

            hw = await save_homework(
                session, homework=descripcion, grade_id=grade.id,
                subject_id=subject_id, delivery_date=delivery,
            )
            subject_str = f" | {subject_name}" if subject_name else ""
            return (
                f"Tarea #{hw.sequence_num} registrada — {grade.name}{subject_str} — {date_str}"
                f"\n  {descripcion}"
            )

        # Múltiples materias — un registro por materia
        lines = [f"Tareas registradas — {grade.name} — {date_str}:"]
        for materia_name in materias:
            subject = await find_subject(session, materia_name)
            subject_id = subject.id if subject else None
            subject_display = subject.name if subject else materia_name

            hw = await save_homework(
                session, homework=descripcion, grade_id=grade.id,
                subject_id=subject_id, delivery_date=delivery,
            )
            lines.append(f"  #{hw.sequence_num} {subject_display}")

        lines.append(f"  Descripcion: {descripcion}")
        return "\n".join(lines)


async def _consultar_tareas(
    cursos: list[str],
    periodo: str = "trimestre",
) -> str:
    """Consulta las tareas registradas de uno o varios cursos."""
    from schoolai.db.connection import async_session
    from schoolai.skills.homework.repository import find_grade
    from schoolai.skills.query.formatter import format_homework_multi
    from schoolai.skills.query.resolver import resolve_homework

    intent = _period_to_dates(periodo, "homework")
    hw_data = []
    not_found = []

    async with async_session() as session:
        for curso in cursos:
            grade = await find_grade(session, curso)
            if not grade:
                not_found.append(curso)
                continue
            data = await resolve_homework(intent, grade.id, session)
            hw_data.append(data)

    if not hw_data:
        return "Sin tareas registradas."

    text = _strip_tags(format_homework_multi(hw_data))
    if not_found:
        text += f"\nCursos no encontrados: {', '.join(not_found)}"
    return text


async def _eliminar_tarea(numero: int, curso: str) -> str:
    """Elimina una tarea por número de secuencia y curso. Las submissions se eliminan en cascada."""
    from schoolai.db.connection import async_session
    from schoolai.skills.homework.repository import (
        delete_homework,
        find_grade,
        find_homework_by_ref,
    )

    async with async_session() as session:
        grade = await find_grade(session, curso)
        if not grade:
            return f"Curso '{curso}' no encontrado."

        hw = await find_homework_by_ref(session, numero, grade.id, any_trimester=True)
        if not hw:
            return f"Tarea #{numero} no encontrada en {grade.name}."

        desc = hw.homework
        seq = hw.sequence_num
        await delete_homework(session, hw.id)

    return f"Tarea #{seq} eliminada — {grade.name}: {desc[:80]}"


async def _listar_cursos(level: str | None = None) -> str:
    """Lista los cursos disponibles, opcionalmente filtrado por nivel educativo."""
    from sqlalchemy import select

    from schoolai.db.connection import async_session
    from schoolai.db.models.grade import Grade

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


async def _listar_actividades() -> str:
    """Lista todas las actividades/cuotas activas."""
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import get_actividades

    async with async_session() as session:
        actividades = await get_actividades(session, only_active=True)

    if not actividades:
        return "No hay actividades activas."

    lines = ["Actividades activas:"]
    lines.extend(f"  [{a.id}] {a.nombre} — ${a.monto:.2f}" for a in actividades)
    return "\n".join(lines)


async def _crear_actividad(
    nombre: str,
    monto: float,
    curso: str | None = None,
) -> str:
    """Crea una nueva actividad o cuota escolar."""
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import create_actividad

    async with async_session() as session:
        actividad = await create_actividad(session, nombre, monto)
        act_id = actividad.id

    lines = [f"Actividad creada: '{nombre}' — ${monto:.2f} (ID: {act_id})"]

    if curso:
        from schoolai.db.connection import async_session as _session
        from schoolai.skills.cuotas.service import add_participantes, get_students_in_grade
        from schoolai.skills.homework.repository import find_grade

        async with _session() as session:
            grade = await find_grade(session, curso)
            if grade:
                students = await get_students_in_grade(session, grade.id)
                count = await add_participantes(session, act_id, [s.id for s in students])
                lines.append(
                    f"  {count} estudiantes de {grade.name} agregados como participantes.",
                )
            else:
                lines.append(
                    f"  Curso '{curso}' no encontrado — participantes no agregados.",
                )

    return "\n".join(lines)


async def _estado_actividad(nombre: str) -> str:
    """Consulta el estado de pagos de una actividad."""
    from schoolai.db.connection import async_session
    from schoolai.skills.cuotas.service import get_actividad_by_nombre, get_estado_actividad

    async with async_session() as session:
        actividad = await get_actividad_by_nombre(session, nombre)
        if not actividad:
            return f"Actividad '{nombre}' no encontrada."
        act, participantes = await get_estado_actividad(session, actividad.id)

    if not act:
        return f"Actividad '{nombre}' no encontrada."

    total = len(participantes)
    pagaron = sum(1 for p in participantes if p.is_complete)
    pendientes = total - pagaron

    lines = [
        f"Actividad: {act.nombre} — ${act.monto:.2f}",
        f"  Pagaron completo: {pagaron}/{total}",
        f"  Pendientes: {pendientes}",
    ]
    if participantes:
        lines.append("  Detalle:")
        for p in participantes:
            icon = "✓" if p.is_complete else "·"
            pagado = float(p.total_pagado or 0)
            lines.append(f"    {icon} Estudiante #{p.student_id}: ${pagado:.2f}")
    return "\n".join(lines)


async def _registrar_pago(
    nombres: list[str],
    monto: float,
    actividad: str,
    curso: str | None = None,
) -> str:
    """Registra el pago de uno o varios estudiantes para una actividad."""
    from schoolai.db.connection import async_session
    from schoolai.skills.attendance.matcher import match_names
    from schoolai.skills.cuotas.service import get_actividad_by_nombre, register_pago
    from schoolai.skills.homework.repository import find_grade

    if not curso:
        return "Se requiere el curso para identificar a los estudiantes."

    async with async_session() as session:
        act = await get_actividad_by_nombre(session, actividad)
        if not act:
            return f"Actividad '{actividad}' no encontrada."

        grade = await find_grade(session, curso)
        if not grade:
            return f"Curso '{curso}' no encontrado."

        extracted = [{"name": n, "status": "F"} for n in nombres]
        matches = await match_names(extracted, grade.id, session)
        resolved = [m for m in matches if m.resolved]

        if not resolved:
            return f"No se encontraron estudiantes: {', '.join(nombres)}"

        registrados = []
        for m in resolved:
            await register_pago(session, act.id, m.matched_id, monto)
            registrados.append(m.matched_name)

    lines = [f"Pagos registrados — {act.nombre} — ${monto:.2f} c/u:"]
    lines.extend(f"  ✓ {name}" for name in registrados)
    not_found = [m.raw_name for m in matches if not m.resolved]
    if not_found:
        lines.append(f"No encontrados: {', '.join(not_found)}")
    return "\n".join(lines)


# ── Python REPL ───────────────────────────────────────────────────────────────


async def _python_repl(code: str) -> str:
    """Ejecuta código Python restringido con acceso de solo lectura a la DB."""
    from schoolai.skills.orchestrator.repl import run_repl

    return await run_repl(code)


# ── Registry ──────────────────────────────────────────────────────────────────


TOOLS: list[ToolDef] = [
    ToolDef(
        name="registrar_asistencia",
        description=(
            "Records absences, tardiness, or justified absences for students in a course. "
            "Use status='all_present' if all students attended."
        ),
        parameters={
            "type": "object",
            "properties": {
                "nombres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Last names or first names of the absent/late students",
                },
                "curso": {
                    "type": "string",
                    "description": "Course abbreviation, e.g.: 3bt, 8egb, prep",
                },
                "fecha": {
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
            },
            "required": ["nombres", "curso"],
        },
        fn=_registrar_asistencia,
    ),
    ToolDef(
        name="consultar_asistencia",
        description="Queries the attendance record for one or more courses.",
        parameters={
            "type": "object",
            "properties": {
                "cursos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Course abbreviations, e.g.: ['3bt', '8egb']",
                },
                "periodo": {
                    "type": "string",
                    "description": "today, yesterday, week, month, trimestre. Default: today",
                },
            },
            "required": ["cursos"],
        },
        fn=_consultar_asistencia,
    ),
    ToolDef(
        name="crear_tarea",
        description="Records a new homework assignment, task, or activity for a course.",
        parameters={
            "type": "object",
            "properties": {
                "descripcion": {
                    "type": "string",
                    "description": "Full description of the homework or assignment",
                },
                "curso": {"type": "string", "description": "Course abbreviation, e.g.: 3bt"},
                "materias": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of subjects. If the teacher names several subjects separated "
                        "by '/' or ',', split them into individual items. "
                        "Use the full subject name as the teacher wrote it. Optional."
                    ),
                },
                "fecha_entrega": {
                    "type": "string",
                    "description": "Due date YYYY-MM-DD. Optional.",
                },
            },
            "required": ["descripcion", "curso"],
        },
        fn=_crear_tarea,
    ),
    ToolDef(
        name="consultar_tareas",
        description="Queries the recorded homework assignments for one or more courses.",
        parameters={
            "type": "object",
            "properties": {
                "cursos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Course abbreviations",
                },
                "periodo": {
                    "type": "string",
                    "description": "today, yesterday, week, month, trimestre. Default: trimestre",
                },
            },
            "required": ["cursos"],
        },
        fn=_consultar_tareas,
    ),
    ToolDef(
        name="eliminar_tarea",
        description=(
            "Permanently deletes a homework assignment by its sequence number and course. "
            "Only call this after the teacher has explicitly confirmed the deletion."
        ),
        parameters={
            "type": "object",
            "properties": {
                "numero": {
                    "type": "integer",
                    "description": "Homework sequence number shown in the list, e.g.: 2",
                },
                "curso": {
                    "type": "string",
                    "description": "Course abbreviation, e.g.: 1bt",
                },
            },
            "required": ["numero", "curso"],
        },
        fn=_eliminar_tarea,
    ),
    ToolDef(
        name="listar_cursos",
        description=(
            "Lists all available courses with their abbreviations. "
            "Call this tool BEFORE consultar_asistencia or consultar_tareas when the teacher "
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
        fn=_listar_cursos,
    ),
    ToolDef(
        name="listar_actividades",
        description="Lists all active school activities and fees (cuotas).",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        fn=_listar_actividades,
    ),
    ToolDef(
        name="crear_actividad",
        description="Creates a new school activity or fee with a name and amount.",
        parameters={
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Activity name"},
                "monto": {"type": "number", "description": "Amount in dollars"},
                "curso": {
                    "type": "string",
                    "description": (
                        "Course abbreviation to auto-enroll students as participants. Optional."
                    ),
                },
            },
            "required": ["nombre", "monto"],
        },
        fn=_crear_actividad,
    ),
    ToolDef(
        name="estado_actividad",
        description="Queries the payment status of an activity by name.",
        parameters={
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Activity name"},
            },
            "required": ["nombre"],
        },
        fn=_estado_actividad,
    ),
    ToolDef(
        name="registrar_pago",
        description="Records a payment from one or more students for an activity.",
        parameters={
            "type": "object",
            "properties": {
                "nombres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Last names of the students who paid",
                },
                "monto": {"type": "number", "description": "Amount paid in dollars"},
                "actividad": {"type": "string", "description": "Activity name"},
                "curso": {"type": "string", "description": "Course abbreviation"},
            },
            "required": ["nombres", "monto", "actividad", "curso"],
        },
        fn=_registrar_pago,
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
]

TOOLS_BY_NAME: dict[str, ToolDef] = {t.name: t for t in TOOLS}


async def execute_tool(name: str, args: dict) -> str:
    """Ejecuta una tool por nombre. Retorna string para el LLM."""
    tool = TOOLS_BY_NAME.get(name)
    if not tool or tool.fn is None:
        return f"Tool '{name}' no encontrada."
    try:
        result = await tool.fn(**args)
        return str(result)
    except Exception as e:  # noqa: BLE001
        logger.error(f"[orchestrator] tool={name} error: {e}")
        return f"Error en '{name}': {e}"
