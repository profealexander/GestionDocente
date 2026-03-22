from __future__ import annotations
from datetime import datetime
from sqlalchemy import Integer, SmallInteger, String, DateTime, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from schoolai.db.connection import Base

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from schoolai.db.models.teacher import Teacher
    from schoolai.db.models.student import Student
    from schoolai.db.models.subject import Subject


class Notification(Base):
    __tablename__ = "notifications"

    id:          Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id:  Mapped[int|None] = mapped_column(Integer, ForeignKey("teachers.id",  ondelete="SET NULL"), nullable=True)
    student_id:  Mapped[int|None] = mapped_column(Integer, ForeignKey("students.id",  ondelete="SET NULL"), nullable=True)
    subject_id:  Mapped[int|None] = mapped_column(Integer, ForeignKey("subjects.id",  ondelete="SET NULL"), nullable=True)
    homework_id: Mapped[int|None] = mapped_column(Integer, ForeignKey("homework.id",  ondelete="SET NULL"), nullable=True)
    type:        Mapped[str]      = mapped_column(String(30), nullable=False, server_default="tarea")
    anio:        Mapped[int]      = mapped_column(SmallInteger, nullable=False)
    teacher_seq: Mapped[int]      = mapped_column(Integer, nullable=False)
    student_seq: Mapped[int]      = mapped_column(Integer, nullable=False)
    num_doc:     Mapped[str]      = mapped_column(String(50), nullable=False, unique=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)

    teacher:  Mapped["Teacher|None"]  = relationship("Teacher",  lazy="joined", foreign_keys=[teacher_id])
    student:  Mapped["Student|None"]  = relationship("Student",  lazy="joined", foreign_keys=[student_id])
    subject:  Mapped["Subject|None"]  = relationship("Subject",  lazy="joined", foreign_keys=[subject_id])
