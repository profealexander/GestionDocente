from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base

if TYPE_CHECKING:
    from schoolai.db.models.teacher import Teacher


class ContextDocument(Base):
    """Documento de contexto cargado por un docente o la institución.

    scope:
        'personal'    — visible solo para el docente que lo subió
        'institution' — visible para todos los docentes

    category:
        'schedule'   — horario del docente
        'calendar'   — calendario / cronograma escolar
        'policies'   — reglamentos, normas, circulares
        'contacts'   — directorio de contactos
        'notes'      — apuntes, recordatorios
        'other'      — general / sin categoría clara

    source_type:
        'text'     — texto plano enviado directamente
        'photo'    — imagen procesada con visión
        'document' — PDF u otro archivo de texto
    """

    __tablename__ = "context_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True,
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False, server_default="personal")
    category: Mapped[str] = mapped_column(String(30), nullable=False, server_default="other")
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="text")
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )

    teacher: Mapped["Teacher | None"] = relationship(
        "Teacher", lazy="joined", foreign_keys=[teacher_id],
    )

    def __repr__(self) -> str:
        return (
            f"<ContextDocument id={self.id} scope={self.scope!r} "
            f"category={self.category!r} title={self.title!r}>"
        )
