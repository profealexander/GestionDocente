"""Operaciones de base de datos para cuotas/actividades."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.cuota import Actividad, ActividadParticipante, ActividadPago
from schoolai.db.models.student import Student


# ── Actividades ───────────────────────────────────────────────────────────────

async def create_actividad(
    session: AsyncSession,
    nombre: str,
    monto: float,
    teacher_id: int | None = None,
    descripcion: str | None = None,
) -> Actividad:
    actividad = Actividad(
        nombre=nombre,
        monto=monto,
        teacher_id=teacher_id,
        descripcion=descripcion,
    )
    session.add(actividad)
    await session.flush()
    await session.refresh(actividad)
    await session.commit()
    return actividad


async def get_actividades(
    session: AsyncSession,
    teacher_id: int | None = None,
    only_active: bool = True,
) -> list[Actividad]:
    stmt = select(Actividad)
    if only_active:
        stmt = stmt.where(Actividad.is_active.is_(True))
    if teacher_id is not None:
        stmt = stmt.where(Actividad.teacher_id == teacher_id)
    return (await session.execute(stmt.order_by(Actividad.created_at.desc()))).scalars().all()


async def get_actividad_by_nombre(
    session: AsyncSession,
    nombre: str,
) -> Actividad | None:
    """Búsqueda fuzzy: retorna la actividad cuyo nombre contiene `nombre`."""
    stmt = select(Actividad).where(
        Actividad.nombre.ilike(f"%{nombre}%"),
        Actividad.is_active.is_(True),
    )
    return (await session.execute(stmt.limit(1))).scalars().first()


# ── Participantes ─────────────────────────────────────────────────────────────

async def add_participantes(
    session: AsyncSession,
    actividad_id: int,
    student_ids: list[int],
) -> int:
    """Agrega estudiantes a una actividad (ignora duplicados). Retorna cuántos se agregaron."""
    added = 0
    for sid in student_ids:
        existing = (await session.execute(
            select(ActividadParticipante).where(
                ActividadParticipante.actividad_id == actividad_id,
                ActividadParticipante.student_id == sid,
            )
        )).scalars().first()
        if not existing:
            session.add(ActividadParticipante(actividad_id=actividad_id, student_id=sid))
            added += 1
    await session.commit()
    return added


async def get_participantes(
    session: AsyncSession,
    actividad_id: int,
) -> list[ActividadParticipante]:
    stmt = (
        select(ActividadParticipante)
        .where(ActividadParticipante.actividad_id == actividad_id)
        .order_by(ActividadParticipante.student_id)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_students_in_grade(session: AsyncSession, grade_id: int) -> list[Student]:
    stmt = select(Student).where(
        Student.grade_id == grade_id,
        Student.is_active.is_(True),
    ).order_by(Student.last_name, Student.first_name)
    return (await session.execute(stmt)).scalars().all()


# ── Pagos ─────────────────────────────────────────────────────────────────────

async def register_pago(
    session: AsyncSession,
    actividad_id: int,
    student_id: int,
    monto: float,
    notas: str | None = None,
    telegram_file_id: str | None = None,
    file_type: str | None = None,
) -> tuple[ActividadPago, ActividadParticipante]:
    """Registra un pago. Crea el participante si no existe. Actualiza totales."""
    # Upsert participante
    participante = (await session.execute(
        select(ActividadParticipante).where(
            ActividadParticipante.actividad_id == actividad_id,
            ActividadParticipante.student_id == student_id,
        )
    )).scalars().first()

    if not participante:
        participante = ActividadParticipante(
            actividad_id=actividad_id,
            student_id=student_id,
            total_pagado=0,
        )
        session.add(participante)
        await session.flush()

    # Crear pago
    pago = ActividadPago(
        participante_id=participante.id,
        monto=monto,
        notas=notas,
        telegram_file_id=telegram_file_id,
        file_type=file_type,
    )
    session.add(pago)
    await session.flush()

    # Actualizar total y completado
    participante.total_pagado = float(participante.total_pagado or 0) + monto
    actividad = await session.get(Actividad, actividad_id)
    if actividad and participante.total_pagado >= float(actividad.monto):
        participante.is_complete = True

    await session.commit()
    await session.refresh(participante)
    return pago, participante


async def get_estado_actividad(
    session: AsyncSession,
    actividad_id: int,
) -> tuple[Actividad | None, list[ActividadParticipante]]:
    """Retorna la actividad y todos sus participantes con pagos cargados."""
    actividad = await session.get(Actividad, actividad_id)
    if not actividad:
        return None, []
    participantes = await get_participantes(session, actividad_id)
    return actividad, participantes
