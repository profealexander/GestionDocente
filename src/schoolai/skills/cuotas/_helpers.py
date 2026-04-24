"""Helpers internos compartidos entre los sub-handlers de cuotas."""

from __future__ import annotations


async def _get_teacher_id(user_id: int) -> int | None:
    from sqlalchemy import select

    from schoolai.db.connection import get_db_session
    from schoolai.db.models.teacher import Teacher

    async with get_db_session() as session:
        return (
            await session.execute(
                select(Teacher.id).where(
                    Teacher.telegram_id == user_id,
                    Teacher.is_active.is_(True),
                ),
            )
        ).scalar_one_or_none()
