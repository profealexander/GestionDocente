"""Tools de cuotas y actividades: list, create, status, register_payment."""

from __future__ import annotations

from sqlalchemy import select

from schoolai.db.connection import get_db_session
from schoolai.db.models.teacher import Teacher
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.cuotas.service import (
    add_participantes,
    create_actividad,
    get_actividad_by_nombre,
    get_actividades,
    get_estado_actividad,
    get_students_in_grade,
    register_pago,
)
from schoolai.skills.homework.repository import find_grade


async def _list_activities(telegram_id: int) -> str:
    """Lists active school activities filtered by the requesting teacher."""
    async with get_db_session() as session:
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
    async with get_db_session() as session:
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
    async with get_db_session() as session:
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

    async with get_db_session() as session:
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
