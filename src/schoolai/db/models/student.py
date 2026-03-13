from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("people.id"), nullable=True)
    section: Mapped[str] = mapped_column(String, nullable=False)
    guardian_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("people.id"), nullable=True)
    grade_id: Mapped[int] = mapped_column(Integer, ForeignKey("grades.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")

    person: Mapped["Person"] = relationship("Person", foreign_keys=[person_id], lazy="joined")  # noqa: F821
    grade: Mapped["Grade"] = relationship("Grade", lazy="joined")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Student id={self.id} person_id={self.person_id} grade_id={self.grade_id}>"
