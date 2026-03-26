"""Modelo para seguimiento de cumplimiento de tareas."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class HomeworkSubmission(Base):
    __tablename__ = "homework_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    homework_id: Mapped[int] = mapped_column(Integer, ForeignKey("homework.id", ondelete="CASCADE"))
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("students.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="missing")
    reported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    homework: Mapped["Homework"] = relationship("Homework", back_populates="submissions")  # noqa: F821
    student: Mapped["Student"] = relationship("Student")  # noqa: F821
