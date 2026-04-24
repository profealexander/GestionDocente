from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("people.id"), nullable=True)
    grade_id: Mapped[int] = mapped_column(Integer, ForeignKey("grades.id"), nullable=False)
    section: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")

    person: Mapped["Person"] = relationship("Person", foreign_keys=[person_id], lazy="joined")  # noqa: F821
    grade: Mapped["Grade"] = relationship("Grade", lazy="joined")  # noqa: F821
    representatives: Mapped[list["StudentRepresentative"]] = relationship(  # noqa: F821
        "StudentRepresentative",
        back_populates="student",
        lazy="selectin",
        primaryjoin="Student.id == StudentRepresentative.student_id",
        order_by="StudentRepresentative.is_primary_notify.desc()",
    )

    @property
    def primary_representative(self) -> "StudentRepresentative | None":  # noqa: F821
        return next(
            (r for r in self.representatives if r.is_primary_notify and r.status == "active"), None,
        )

    def __repr__(self) -> str:
        return f"<Student id={self.id} person_id={self.person_id} grade_id={self.grade_id}>"
