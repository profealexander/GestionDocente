from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base

if TYPE_CHECKING:
    from schoolai.db.models.grade import Grade
    from schoolai.db.models.teacher import Teacher


class Reminder(Base):
    """Recordatorio programado por un docente.

    target:
        'teacher'  — solo Telegram al docente
        'parents'  — solo WhatsApp a representantes del curso
        'both'     — ambos canales
    status:
        'pending'   — esperando ser enviado
        'sent'      — enviado exitosamente
        'failed'    — error al enviar
        'cancelled' — cancelado manualmente
    """

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True,
    )
    grade_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("grades.id", ondelete="SET NULL"), nullable=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(String(20), nullable=False, server_default="teacher")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )

    teacher: Mapped["Teacher | None"] = relationship(
        "Teacher", lazy="joined", foreign_keys=[teacher_id],
    )
    grade: Mapped["Grade | None"] = relationship(
        "Grade", lazy="joined", foreign_keys=[grade_id],
    )

    def __repr__(self) -> str:
        return (
            f"<Reminder id={self.id} target={self.target!r} "
            f"status={self.status!r} at={self.scheduled_at}>"
        )
