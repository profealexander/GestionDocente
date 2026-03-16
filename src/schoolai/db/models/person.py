from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from schoolai.db.connection import Base


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    second_last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    national_id: Mapped[str | None] = mapped_column(String, nullable=True)
    passport: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    current_position: Mapped[str | None] = mapped_column(String, nullable=True)
    current_institution: Mapped[str | None] = mapped_column(String, nullable=True)
    previous_institution: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    telegram_handle: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")

    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name, self.second_last_name]
        return " ".join(p for p in parts if p)

    def __repr__(self) -> str:
        return f"<Person id={self.id} name={self.full_name()!r}>"
