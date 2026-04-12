"""Modelo de notas académicas por estudiante, materia, trimestre y columna."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class StudentScore(Base):
    __tablename__ = "student_scores"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "subject_id", "trimester_num", "column_label",
            name="uq_student_score",
        ),
        Index("ix_student_scores_lookup", "grade_id", "subject_id", "trimester_num"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False,
    )
    subject_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False,
    )
    grade_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("grades.id", ondelete="CASCADE"), nullable=False,
    )
    teacher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True,
    )
    trimester_num: Mapped[int] = mapped_column(Integer, nullable=False)
    # Etiqueta libre definida por el docente: "P1", "Lección 1", "Examen", etc.
    column_label: Mapped[str] = mapped_column(String(50), nullable=False)
    # Escala 0.00 – 10.00
    score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    student: Mapped["Student"] = relationship("Student", lazy="joined")  # noqa: F821
    subject: Mapped["Subject"] = relationship("Subject", lazy="joined")  # noqa: F821
    grade: Mapped["Grade"] = relationship("Grade", lazy="joined")  # noqa: F821
