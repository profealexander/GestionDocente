from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class StudentRepresentative(Base):
    """Many-to-many entre students y people (representantes).

    Un estudiante puede tener varios representantes (padre, madre, abuelo…).
    is_primary_notify=True marca al único responsable de recibir notificaciones.
    """

    __tablename__ = "student_representatives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False,
    )
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("people.id", ondelete="CASCADE"), nullable=False,
    )
    relationship_type: Mapped[str | None] = mapped_column(
        String, nullable=True,
    )  # "padre","madre","abuelo","tío","otro"
    is_primary_notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")

    student: Mapped["Student"] = relationship("Student", back_populates="representatives", lazy="joined")  # noqa: F821
    person: Mapped["Person"] = relationship("Person", lazy="joined")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<StudentRep student={self.student_id} "
            f"person={self.person_id} primary={self.is_primary_notify}>"
        )
