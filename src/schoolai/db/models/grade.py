from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from schoolai.db.connection import Base


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<Grade id={self.id} name={self.name!r}>"
