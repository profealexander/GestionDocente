"""Lógica de numeración y persistencia de notificaciones."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.notification import Notification
from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.db.models.teacher import Teacher


def _iniciales(first_name: str, last_name: str) -> str:
    f = (first_name[0] if first_name else "X").upper()
    ln = (last_name[0] if last_name else "X").upper()
    return f + ln


async def _get_teacher_iniciales(teacher_id: int, session: AsyncSession) -> str:
    teacher = await session.get(Teacher, teacher_id)
    if not teacher:
        return "XX"
    person = await session.get(Person, teacher.person_id)
    if not person:
        return "XX"
    return _iniciales(person.first_name or "", person.last_name or "")


async def _get_student_iniciales(student_id: int, session: AsyncSession) -> str:
    student = await session.get(Student, student_id)
    if not student or not student.person:
        return "XX"
    p: Person = student.person
    return _iniciales(p.first_name or "", p.last_name or "")


async def register_notification(
    teacher_id: int,
    student_id: int,
    subject_id: int | None,
    homework_id: int | None,
    notif_type: str,
    session: AsyncSession,
) -> Notification:
    """
    Registra una notificación y genera num_doc secuencial.
    Formato: NOT-{anio}-{ini_docente}-{teacher_seq:03d}-{ini_estudiante}-{student_seq:02d}
    El UNIQUE constraint en num_doc actúa como red de seguridad ante colisiones.
    """
    anio = date.today().year

    # Bloqueo optimista: leer conteos dentro de la transacción activa
    teacher_seq: int = (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.teacher_id == teacher_id,
                Notification.anio == anio,
            ),
        )
    ).scalar() + 1

    student_seq: int = (
        await session.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.teacher_id == teacher_id,
                Notification.student_id == student_id,
                Notification.anio == anio,
            ),
        )
    ).scalar() + 1

    teacher_ini = await _get_teacher_iniciales(teacher_id, session)
    student_ini = await _get_student_iniciales(student_id, session)

    # NOT-2026-EE-007-CE-03-160326
    fecha = date.today()
    fecha_str = f"{fecha.day:02d}{fecha.month:02d}{str(fecha.year)[2:]}"
    num_doc = (
        f"NOT-{anio}-{teacher_ini}-{teacher_seq:03d}-{student_ini}-{student_seq:02d}-{fecha_str}"
    )

    notif = Notification(
        teacher_id=teacher_id,
        student_id=student_id,
        subject_id=subject_id,
        homework_id=homework_id,
        type=notif_type,
        anio=anio,
        teacher_seq=teacher_seq,
        student_seq=student_seq,
        num_doc=num_doc,
    )
    session.add(notif)
    await session.flush()
    return notif
