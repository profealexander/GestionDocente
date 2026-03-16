from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from schoolai.db.connection import Base


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nivel educativo: "inicial" | "egb" | "bachillerato"
    level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Subnivel: "inicial_1" | "inicial_2" | "preparatoria" | "basica_elemental"
    #           | "basica_media" | "basica_superior" | null (bachillerato)
    sublevel: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def __repr__(self) -> str:
        return f"<Grade id={self.id} name={self.name!r}>"
