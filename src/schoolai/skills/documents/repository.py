"""Obtiene datos de la DB para generar documentos."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.grade import Grade
from schoolai.db.models.homework import Homework
from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.db.models.student_representative import StudentRepresentative
from schoolai.db.models.teacher import Teacher
from sqlalchemy import select
from schoolai.skills.documents.generator import NotificacionContext

MONTHS_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

HOLIDAYS = {
    # Feriados Ecuador — año lectivo 2025-2026
    date(2025, 11,  2), date(2025, 11,  3),
    date(2025, 12, 25), date(2026,  1,  1),
    date(2026,  2, 16), date(2026,  2, 17),
    date(2026,  4, 10), date(2026,  4, 13),
    date(2026,  5,  1), date(2026,  5, 25),
}


def _fecha_larga(d: date) -> str:
    return f"{d.day} de {MONTHS_ES[d.month]} de {d.year}"


def _add_business_days(start: date, days: int) -> date:
    d = start
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in HOLIDAYS:
            added += 1
    return d


async def get_notificacion_context(
    student_id: int,
    hw_id: int,
    teacher_id: int,
    num_doc: str,
    session: AsyncSession,
) -> NotificacionContext:
    """Construye NotificacionContext con datos reales de la BD."""
    today = date.today()

    # Estudiante
    student = await session.get(Student, student_id)
    person: Person = student.person
    student_name = f"{person.first_name} {person.last_name}".strip()

    # Curso
    grade = await session.get(Grade, student.grade_id)
    grade_name = grade.name if grade else ""

    # Representante principal
    rep_stmt = (
        select(StudentRepresentative)
        .where(
            StudentRepresentative.student_id == student_id,
            StudentRepresentative.is_primary_notify.is_(True),
            StudentRepresentative.status == "active",
        )
        .limit(1)
    )
    rep_row = (await session.execute(rep_stmt)).scalars().first()
    if rep_row:
        rep_person = await session.get(Person, rep_row.person_id)
        representante = f"{rep_person.first_name} {rep_person.last_name}".strip() if rep_person else "Representante Legal"
    else:
        representante = "Representante Legal"

    # Docente
    teacher = await session.get(Teacher, teacher_id)
    teacher_person = await session.get(Person, teacher.person_id)
    docente_nombre = f"{teacher_person.first_name} {teacher_person.last_name}".strip() if teacher_person else ""
    docente_cargo = (teacher_person.title or "DOCENTE") if teacher_person else "DOCENTE"

    # Tarea
    hw = await session.get(Homework, hw_id)
    asignatura = hw.subject.name if (hw and hw.subject) else "Asignación"
    descripcion = hw.homework if hw else ""
    fecha_programada = hw.delivery_date.strftime("%d/%m/%Y") if (hw and hw.delivery_date) else "Sin fecha"

    fecha_limite = _add_business_days(today, 2)

    return NotificacionContext(
        num_doc=num_doc,
        fecha=_fecha_larga(today),
        representante=representante,
        estudiante=student_name,
        curso=grade_name,
        asignatura=asignatura,
        descripcion=descripcion,
        fecha_programada=fecha_programada,
        fecha_limite=_fecha_larga(fecha_limite),
        docente_nombre=docente_nombre,
        docente_cargo=docente_cargo,
    )
