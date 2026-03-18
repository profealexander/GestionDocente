from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from schoolai.db.connection import Base


class Actividad(Base):
    __tablename__ = "actividades"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id:  Mapped[int | None]    = mapped_column(Integer, ForeignKey("teachers.id"), nullable=True)
    nombre:      Mapped[str]           = mapped_column(String(120), nullable=False)
    descripcion: Mapped[str | None]    = mapped_column(Text, nullable=True)
    monto:       Mapped[float]         = mapped_column(Numeric(10, 2), nullable=False)
    is_active:   Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    created_at:  Mapped[datetime]      = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    teacher: Mapped["Teacher | None"] = relationship("Teacher", lazy="joined")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Actividad id={self.id} nombre={self.nombre!r} monto={self.monto}>"


class ActividadParticipante(Base):
    __tablename__ = "actividad_participantes"
    __table_args__ = (
        UniqueConstraint("actividad_id", "student_id", name="uq_actividad_student"),
    )

    id:           Mapped[int]   = mapped_column(Integer, primary_key=True, autoincrement=True)
    actividad_id: Mapped[int]   = mapped_column(Integer, ForeignKey("actividades.id"), nullable=False)
    student_id:   Mapped[int]   = mapped_column(Integer, ForeignKey("students.id"), nullable=False)
    total_pagado: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    is_complete:  Mapped[bool]  = mapped_column(Boolean, default=False, nullable=False)
    created_at:   Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # lazy="joined": siempre necesitamos actividad y estudiante al cargar participante
    actividad: Mapped["Actividad"]            = relationship("Actividad", lazy="joined")
    student:   Mapped["Student"]              = relationship("Student",   lazy="joined")  # noqa: F821
    # lazy="selectin": carga todos los abonos en una sola query extra (evita N+1)
    pagos:     Mapped[list["ActividadPago"]]  = relationship(
        "ActividadPago",
        back_populates="participante",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ActividadPago.paid_at",
    )

    def __repr__(self) -> str:
        return f"<ActividadParticipante id={self.id} student_id={self.student_id} total={self.total_pagado}>"


class ActividadPago(Base):
    __tablename__ = "actividad_pagos"

    id:               Mapped[int]        = mapped_column(Integer, primary_key=True, autoincrement=True)
    participante_id:  Mapped[int]        = mapped_column(Integer, ForeignKey("actividad_participantes.id"), nullable=False)
    monto:            Mapped[float]      = mapped_column(Numeric(10, 2), nullable=False)
    paid_at:          Mapped[datetime]   = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notas:            Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    file_type:        Mapped[str | None] = mapped_column(String(16), nullable=True)  # 'photo' | 'document'

    participante: Mapped["ActividadParticipante"] = relationship(
        "ActividadParticipante", back_populates="pagos", lazy="joined"
    )

    def __repr__(self) -> str:
        return f"<ActividadPago id={self.id} participante_id={self.participante_id} monto={self.monto}>"
