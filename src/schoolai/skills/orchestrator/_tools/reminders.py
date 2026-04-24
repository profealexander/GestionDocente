"""Tools de recordatorios: create, list, cancel."""

from __future__ import annotations

from schoolai.skills.reminders.tools import cancel_reminder, create_reminder, list_reminders


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
