from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from schoolai.db.connection import Base


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sublevel: Mapped[str] = mapped_column(String(20), nullable=False)

    def __repr__(self) -> str:
        return f"<Subject id={self.id} name={self.name!r}>"
