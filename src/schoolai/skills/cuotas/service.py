"""Operaciones de base de datos para cuotas/actividades."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.cuota import Actividad, ActividadPago, ActividadParticipante
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


async def update_actividad(
    session: AsyncSession,
    actividad_id: int,
    nombre: str | None = None,
    monto: float | None = None,
    descripcion: str | None = None,
    is_active: bool | None = None,
) -> Actividad | None:
    actividad = await session.get(Actividad, actividad_id)
    if not actividad:
        return None
    if nombre is not None:
        actividad.nombre = nombre
    if monto is not None:
        actividad.monto = monto
    if descripcion is not None:
        actividad.descripcion = descripcion
    if is_active is not None:
        actividad.is_active = is_active
    await session.commit()
    await session.refresh(actividad)
    return actividad


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
    if not student_ids:
        return 0

    # Batch SELECT — una sola query para todos los IDs
    existing_ids = set(
        (
            await session.execute(
                select(ActividadParticipante.student_id).where(
                    ActividadParticipante.actividad_id == actividad_id,
                    ActividadParticipante.student_id.in_(student_ids),
                )
            )
        ).scalars().all()
    )

    to_add = [
        ActividadParticipante(actividad_id=actividad_id, student_id=sid)
        for sid in student_ids
        if sid not in existing_ids
    ]
    session.add_all(to_add)
    await session.commit()
    return len(to_add)


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
    from schoolai.db.models.person import Person

    stmt = (
        select(Student)
        .join(Student.person)
        .where(
            Student.grade_id == grade_id,
            Student.status == "active",
        )
        .order_by(Person.last_name, Person.first_name)
    )
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
    participante = (
        (
            await session.execute(
                select(ActividadParticipante).where(
                    ActividadParticipante.actividad_id == actividad_id,
                    ActividadParticipante.student_id == student_id,
                ),
            )
        )
        .scalars()
        .first()
    )

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


async def find_or_create_student(
    session: AsyncSession,
    name: str,
    grade_id: int,
) -> tuple[int, bool]:
    """Busca un estudiante por nombre fuzzy en el grado dado.

    Retorna (student_id, was_created).
    Si no existe, crea Person + Student minimal y retorna (id, True).
    """
    from schoolai.skills.attendance.matcher import match_names

    results = await match_names([{"name": name, "status": "F"}], grade_id, session)
    if results and results[0].matched_id:
        return results[0].matched_id, False

    # Crear registro minimal: parsear nombre en partes
    parts = name.strip().split()
    if len(parts) == 1:
        first_name, last_name = parts[0].title(), "—"
    elif len(parts) == 2:
        first_name, last_name = parts[0].title(), parts[1].title()
    elif len(parts) == 3:
        first_name, last_name = parts[0].title(), parts[1].title()
        second_last = parts[2].title()
    else:
        first_name = parts[0].title()
        last_name = parts[1].title()
        second_last = parts[2].title() if len(parts) > 2 else None

    from schoolai.db.models.person import Person

    person = Person(
        first_name=first_name,
        last_name=last_name,
        second_last_name=locals().get("second_last"),
        role="student",
        status="active",
    )
    session.add(person)
    await session.flush()

    student = Student(person_id=person.id, grade_id=grade_id, section="A", status="active")
    session.add(student)
    await session.flush()
    await session.commit()
    return student.id, True


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
