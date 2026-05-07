"""Funciones async para los LLM tools de recordatorios.

Importadas por skills/orchestrator/tools.py para registrarlas en TOOLS.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_ECUADOR_TZ = timezone(timedelta(hours=-5))


def _parse_dt(value: str) -> datetime:
    """Parsea ISO string. Si no tiene timezone, asume Ecuador (UTC-5)."""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_ECUADOR_TZ)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(tz=timezone.utc) + timedelta(hours=1)


async def create_reminder(
    telegram_id: int,
    message: str,
    scheduled_at: str,
    target: str = "teacher",
    course: str | None = None,
) -> str:
    """Crea un recordatorio programado.

    target: 'teacher' | 'parents' | 'both'
    course: abreviatura del curso (requerido si target incluye 'parents')
    """
    from sqlalchemy import select

    from schoolai.db.connection import get_db_session
    from schoolai.db.models.teacher import Teacher
    from schoolai.skills.homework.repository import find_grade
    from schoolai.skills.reminders.repository import create_reminder as _create

    if target not in ("teacher", "parents", "both"):
        return f"target inválido: '{target}'. Usa 'teacher', 'parents' o 'both'."

    needs_grade = target in ("parents", "both")
    if needs_grade and not course:
        return "Se requiere 'course' cuando target es 'parents' o 'both'."

    dt = _parse_dt(scheduled_at)

    async with get_db_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not teacher:
            return "No se encontró tu perfil de docente."

        grade_id: int | None = None
        grade_name = ""
        if needs_grade and course:
            grade = await find_grade(session, course)
            if not grade:
                return f"Curso '{course}' no encontrado."
            grade_id = grade.id
            grade_name = grade.name

        reminder = await _create(
            session,
            teacher_id=teacher.id,
            message=message,
            target=target,
            scheduled_at=dt,
            grade_id=grade_id,
        )

    # Formato legible en Ecuador local time
    local_dt = dt.astimezone(_ECUADOR_TZ)
    when = local_dt.strftime("%d/%m/%Y %H:%M")
    channel = {"teacher": "Telegram (tú)", "parents": f"WhatsApp ({grade_name})", "both": f"Telegram + WhatsApp ({grade_name})"}[target]

    return (
        f"Recordatorio #{reminder.id} guardado.\n"
        f"  Cuándo: {when}\n"
        f"  Canal:  {channel}\n"
        f"  Mensaje: {message[:80]}"
    )


async def list_reminders(telegram_id: int, status: str = "pending") -> str:
    """Lista los recordatorios del docente.

    status: 'pending' | 'sent' | 'failed' | 'cancelled' | 'all'
    """
    from sqlalchemy import select

    from schoolai.db.connection import get_db_session
    from schoolai.db.models.teacher import Teacher
    from schoolai.skills.reminders.repository import list_teacher_reminders

    async with get_db_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not teacher:
            return "No se encontró tu perfil de docente."

        filter_status = None if status == "all" else status
        reminders = await list_teacher_reminders(
            session, teacher.id, status=filter_status, limit=15,
        )

    if not reminders:
        label = "pendientes" if status == "pending" else status
        return f"No hay recordatorios {label}."

    lines = [f"Recordatorios ({status}):"]
    for r in reminders:
        local_dt = r.scheduled_at.astimezone(_ECUADOR_TZ)
        when = local_dt.strftime("%d/%m %H:%M")
        grade = r.grade.name if r.grade else "—"
        icon = {"pending": "⏳", "sent": "✅", "failed": "❌", "cancelled": "🚫"}.get(r.status, "·")
        lines.append(f"  {icon} #{r.id} [{when}] {r.target} {grade}: {r.message[:50]}")
    return "\n".join(lines)


async def cancel_reminder(telegram_id: int, reminder_id: int) -> str:
    """Cancela un recordatorio pendiente."""
    from sqlalchemy import select

    from schoolai.db.connection import get_db_session
    from schoolai.db.models.teacher import Teacher
    from schoolai.skills.reminders.repository import cancel_reminder as _cancel

    async with get_db_session() as session:
        teacher = (
            await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
        ).scalar_one_or_none()
        if not teacher:
            return "No se encontró tu perfil de docente."

        ok = await _cancel(session, reminder_id, teacher.id)

    if ok:
        return f"Recordatorio #{reminder_id} cancelado."
    return (
        f"No se pudo cancelar el recordatorio #{reminder_id}. "
        "Verifica que sea tuyo, que exista y que esté pendiente."
    )
