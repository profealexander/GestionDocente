from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class TeacherAbsence(Base):
    """Ausencia del docente durante la jornada escolar.

    scope="period" → faltó a un período específico
    scope="day"    → no asistió en toda la jornada
    reason         → código: meeting | permit | sick | other
    reason_label   → texto legible o descripción libre (cuando reason=other)
    """

    __tablename__ = "teacher_absences"
    __table_args__ = (
        Index("ix_teacher_absences_teacher_date", "teacher_id", "date"),
        Index("ix_teacher_absences_date", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teachers.id"), nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    scope: Mapped[str] = mapped_column(String(10), nullable=False)   # "period" | "day"
    period_num: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    grade_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("grades.id"), nullable=True,
    )
    subject_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    period_start: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "09:00"
    period_end: Mapped[str | None] = mapped_column(String(5), nullable=True)    # "09:45"
    reason: Mapped[str] = mapped_column(String(20), nullable=False)   # meeting|permit|sick|other
    reason_label: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    teacher: Mapped["Teacher"] = relationship("Teacher", lazy="select")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<TeacherAbsence teacher={self.teacher_id} date={self.date} "
            f"scope={self.scope} period={self.period_num}>"
        )
