from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from schoolai.db.connection import Base


class Attendance(Base):
    __tablename__ = "attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("students.id"), nullable=True,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(1), nullable=False)  # A | T
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    recorded_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("people.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Attendance student_id={self.student_id} date={self.date} status={self.status}>"
