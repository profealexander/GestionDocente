"""CRUD de recordatorios."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.reminder import Reminder


async def create_reminder(
    session: AsyncSession,
    teacher_id: int,
    message: str,
    target: str,
    scheduled_at: datetime,
    grade_id: int | None = None,
) -> Reminder:
    r = Reminder(
        teacher_id=teacher_id,
        grade_id=grade_id,
        message=message,
        target=target,
        scheduled_at=scheduled_at,
        status="pending",
    )
    session.add(r)
    await session.commit()
    await session.refresh(r)
    return r


async def get_due_reminders(session: AsyncSession, limit: int = 50) -> list[Reminder]:
    """Recordatorios pendientes cuya hora ya llegó — marca como 'sending' de forma atómica.

    El status 'sending' impide que un segundo dispatcher (ej: bot agente corriendo
    en paralelo) procese el mismo lote.  Si el proceso muere antes de marcar
    'sent'/'failed', los recordatorios quedan en 'sending' y no se reenvían.
    Máximo `limit` por corrida.
    """
    now = datetime.now(tz=timezone.utc)
    result = await session.execute(
        select(Reminder).where(
            and_(Reminder.status == "pending", Reminder.scheduled_at <= now),
        ).order_by(Reminder.scheduled_at).limit(limit),
    )
    reminders = list(result.scalars().all())
    for r in reminders:
        r.status = "sending"
    await session.commit()
    return reminders


async def list_teacher_reminders(
    session: AsyncSession,
    teacher_id: int,
    status: str | None = None,
    limit: int = 10,
) -> list[Reminder]:
    stmt = select(Reminder).where(Reminder.teacher_id == teacher_id)
    if status:
        stmt = stmt.where(Reminder.status == status)
    stmt = stmt.order_by(Reminder.scheduled_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def mark_sent(session: AsyncSession, reminder_id: int, ok: bool) -> None:
    r = await session.get(Reminder, reminder_id)
    if r:
        r.status = "sent" if ok else "failed"
        r.sent_at = datetime.now(tz=timezone.utc)
        await session.commit()


async def cancel_reminder(session: AsyncSession, reminder_id: int, teacher_id: int) -> bool:
    """Cancela un recordatorio. Solo el docente dueño puede cancelarlo. Retorna True si ok."""
    r = await session.get(Reminder, reminder_id)
    if not r or r.teacher_id != teacher_id or r.status not in ("pending",):
        return False
    r.status = "cancelled"
    await session.commit()
    return True
