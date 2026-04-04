"""Notificación consolidada de inasistencias al docente tutor al fin de jornada.

Flujo:
  _finish_jornada() → notify_tutors_end_of_day()
    → consulta attendance de hoy agrupado por grade
    → para cada grade con ausencias, busca el tutor
    → envía WhatsApp consolidado al tutor con lista de ausentes
"""

from __future__ import annotations

from datetime import date

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.connection import async_session
from schoolai.db.models.teacher import TeacherPosition, Teacher
from schoolai.db.models.grade import Grade
from schoolai.db.models.student import Student
from schoolai.config import settings
from schoolai.skills.whatsapp.sender import send_whatsapp


async def notify_tutors_end_of_day() -> int:
    """Envía resumen de inasistencias del día a cada tutor de curso.
    Retorna el número de tutores notificados."""

    if not settings.green_api_instance or not settings.green_api_token:
        logger.warning("[tutor_notify] Green API no configurada — saltando notificación")
        return 0

    today = date.today()
    notified = 0

    async with async_session() as session:
        absences_by_grade = await _get_today_absences(session, today)
        if not absences_by_grade:
            logger.info("[tutor_notify] sin ausencias hoy — nada que notificar")
            return 0

        for grade_id, students in absences_by_grade.items():
            tutor = await _get_tutor(session, grade_id)
            if not tutor:
                logger.info(f"[tutor_notify] grade={grade_id} sin tutor registrado")
                continue
            if not tutor.whatsapp_phone:
                logger.info(
                    f"[tutor_notify] tutor={tutor.id} grade={grade_id} sin WhatsApp",
                )
                continue

            grade = await session.get(Grade, grade_id)
            grade_name = grade.name if grade else f"Curso {grade_id}"
            message = _build_message(grade_name, students, today)

            ok = await send_whatsapp(
                settings.green_api_instance,
                settings.green_api_token,
                tutor.whatsapp_phone,
                message,
            )
            if ok:
                notified += 1
                logger.info(
                    f"[tutor_notify] notificado tutor={tutor.id} grade={grade_name} "
                    f"ausentes={len(students)}",
                )
            else:
                logger.warning(f"[tutor_notify] fallo envío tutor={tutor.id} grade={grade_name}")

    return notified


async def _get_today_absences(
    session: AsyncSession, today: date,
) -> dict[int, list[dict]]:
    """Retorna dict {grade_id: [{name, status, subject}]} con ausencias del día."""
    from schoolai.db.models.attendance import Attendance

    records = (
        (
            await session.execute(
                select(Attendance)
                .where(
                    Attendance.date == today,
                    Attendance.status.in_(["absent", "late", "justified"]),
                )
            )
        )
        .scalars()
        .all()
    )

    if not records:
        return {}

    result: dict[int, list[dict]] = {}
    for rec in records:
        student = await session.get(Student, rec.student_id)
        if not student or not student.person:
            continue
        grade_id = student.grade_id
        name = f"{student.person.first_name} {student.person.last_name}"
        result.setdefault(grade_id, []).append({
            "name": name,
            "status": rec.status,
        })

    return result


async def _get_tutor(session: AsyncSession, grade_id: int) -> Teacher | None:
    """Retorna el docente tutor activo del curso."""
    position = (
        await session.execute(
            select(TeacherPosition).where(
                TeacherPosition.grade_id == grade_id,
                TeacherPosition.position_type == "tutor",
                TeacherPosition.is_active == True,  # noqa: E712
            )
        )
    ).scalar_one_or_none()

    if not position:
        return None
    return await session.get(Teacher, position.teacher_id)


def _build_message(grade_name: str, students: list[dict], today: date) -> str:
    _STATUS = {"absent": "Falta", "late": "Atraso", "justified": "Justificado"}
    date_str = today.strftime("%d/%m/%Y")
    lines = [
        f"📋 Reporte de inasistencias — {grade_name}",
        f"Fecha: {date_str}",
        "",
    ]
    for s in students:
        status_label = _STATUS.get(s["status"], s["status"])
        lines.append(f"• {s['name']} — {status_label}")
    lines += [
        "",
        "— SchoolAI",
    ]
    return "\n".join(lines)
