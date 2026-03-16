from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class Homework(Base):
    __tablename__ = "homework"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    homework: Mapped[str] = mapped_column(Text, nullable=False)
    grade_id: Mapped[int] = mapped_column(Integer, ForeignKey("grades.id"), nullable=False)
    subject_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("subjects.id"), nullable=True)
    submission_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivery_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sequence_num: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trimester_num: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    grade: Mapped["Grade"] = relationship("Grade", lazy="joined")  # noqa: F821
    subject: Mapped["Subject"] = relationship("Subject", lazy="joined")  # noqa: F821
    submissions: Mapped[list["HomeworkSubmission"]] = relationship("HomeworkSubmission", back_populates="homework", cascade="all, delete-orphan")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Homework id={self.id} grade_id={self.grade_id}>"
