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
    """Registra una nueva tarea o actividad para un curso."""
    from schoolai.db.connection import async_session
    from schoolai.skills.homework.repository import find_grade, find_subject, save_homework

    materias = materias or []
    delivery = _parse_date(fecha_entrega) if fecha_entrega else None

    async with async_session() as session:
        grade = await find_grade(session, curso)
        if not grade:
            return f"Curso '{curso}' no encontrado."

        if materias:
            subject = await find_subject(session, materias[0])
            subject_id = subject.id if subject else None
            subject_name = subject.name if subject else materias[0]
        else:
            subject_id = None
            subject_name = None

        hw = await save_homework(
            session,
            homework=descripcion,
            grade_id=grade.id,
            subject_id=subject_id,
            delivery_date=delivery,
        )

    date_str = hw.delivery_date.strftime("%d/%m/%Y") if hw.delivery_date else "sin fecha"
    subject_str = f" | {subject_name}" if subject_name else ""
    return (
        f"Tarea #{hw.sequence_num} registrada — {grade.name}{subject_str} — {date_str}"
        f"\n  {descripcion}"
    )


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


# ── Registry ──────────────────────────────────────────────────────────────────


TOOLS: list[ToolDef] = [
    ToolDef(
        name="registrar_asistencia",
        description=(
            "Registra faltas, atrasos o justificados de estudiantes en un curso. "
            "Usa status='all_present' si todos asistieron."
        ),
        parameters={
            "type": "object",
            "properties": {
                "nombres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Apellidos o nombres de los estudiantes ausentes/atrasados",
                },
                "curso": {
                    "type": "string",
                    "description": "Abreviatura del curso, ej: 3bt, 8egb, prep",
                },
                "fecha": {
                    "type": "string",
                    "description": "today, yesterday, o YYYY-MM-DD. Default: today",
                },
                "status": {
                    "type": "string",
                    "enum": ["absent", "late", "justified", "all_present"],
                    "description": (
                        "absent=falta, late=atraso, "
                        "justified=justificado, all_present=todos presentes"
                    ),
                },
            },
            "required": ["nombres", "curso"],
        },
        fn=_registrar_asistencia,
    ),
    ToolDef(
        name="consultar_asistencia",
        description="Consulta el registro de asistencia de uno o varios cursos.",
        parameters={
            "type": "object",
            "properties": {
                "cursos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Abreviaturas de cursos, ej: ['3bt', '8egb']",
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
        description="Registra una nueva tarea, deber o actividad para un curso.",
        parameters={
            "type": "object",
            "properties": {
                "descripcion": {
                    "type": "string",
                    "description": "Descripción completa de la tarea",
                },
                "curso": {"type": "string", "description": "Abreviatura del curso, ej: 3bt"},
                "materias": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de materias. Opcional.",
                },
                "fecha_entrega": {
                    "type": "string",
                    "description": "Fecha YYYY-MM-DD. Opcional.",
                },
            },
            "required": ["descripcion", "curso"],
        },
        fn=_crear_tarea,
    ),
    ToolDef(
        name="consultar_tareas",
        description="Consulta las tareas registradas de uno o varios cursos.",
        parameters={
            "type": "object",
            "properties": {
                "cursos": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Abreviaturas de cursos",
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
        name="listar_actividades",
        description="Lista todas las actividades/cuotas escolares activas.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        fn=_listar_actividades,
    ),
    ToolDef(
        name="crear_actividad",
        description="Crea una nueva actividad o cuota escolar con nombre y monto.",
        parameters={
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la actividad"},
                "monto": {"type": "number", "description": "Monto en dólares"},
                "curso": {
                    "type": "string",
                    "description": (
                        "Abreviatura del curso para agregar participantes. Opcional."
                    ),
                },
            },
            "required": ["nombre", "monto"],
        },
        fn=_crear_actividad,
    ),
    ToolDef(
        name="estado_actividad",
        description="Consulta el estado de pagos de una actividad por nombre.",
        parameters={
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la actividad"},
            },
            "required": ["nombre"],
        },
        fn=_estado_actividad,
    ),
    ToolDef(
        name="registrar_pago",
        description="Registra el pago de uno o varios estudiantes para una actividad.",
        parameters={
            "type": "object",
            "properties": {
                "nombres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Apellidos de los estudiantes que pagan",
                },
                "monto": {"type": "number", "description": "Monto pagado en dólares"},
                "actividad": {"type": "string", "description": "Nombre de la actividad"},
                "curso": {"type": "string", "description": "Abreviatura del curso"},
            },
            "required": ["nombres", "monto", "actividad", "curso"],
        },
        fn=_registrar_pago,
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
