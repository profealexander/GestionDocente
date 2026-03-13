from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.skills.homework.detector import (
    extract_course,
    extract_date,
    extract_subject,
    is_homework_message,
)
from schoolai.skills.homework.repository import find_grade, find_subject, save_homework


@dataclass
class AgentResult:
    saved: bool
    message: str
    homework_id: int | None = None
    grade_name: str | None = None
    subject_name: str | None = None
    waiting_for_subject: bool = False
    pending_grade_id: int | None = None
    pending_grade_name: str | None = None
    pending_delivery: date | None = None


async def process(text: str, session: AsyncSession) -> AgentResult:
    if not is_homework_message(text):
        return AgentResult(
            saved=False,
            message=(
                "Para registrar una tarea necesito que indiques:\n"
                "• *Qué* hay que hacer (tarea, actividad, proyecto...)\n"
                "• *Curso* (ej: tercero BT, décimo EGB)\n"
                "• *Asignatura* (ej: Matemáticas, Física)\n\n"
                "Ejemplo: _Tarea de Matemáticas para 3ro BT: resolver página 45 para el viernes._"
            ),
        )

    course_text = extract_course(text)
    if not course_text:
        return AgentResult(
            saved=False,
            message=(
                "Entendido, parece una tarea. Pero no identifiqué el *curso*.\n\n"
                "Por favor indica el curso. Ejemplos:\n"
                "• _1ro BT_, _2do BT_, _3ro BT_\n"
                "• _Décimo EGB_, _Noveno EGB_\n\n"
                "Reenvía el mensaje incluyendo el curso."
            ),
        )

    grade = await find_grade(session, course_text)
    if not grade:
        return AgentResult(
            saved=False,
            message=(
                f"No encontré el curso *{course_text}* en el sistema.\n\n"
                "Los cursos disponibles son:\n"
                "• Básica: Segundo EGB al Décimo EGB\n"
                "• Bachillerato: 1ro BT, 2do BT, 3ro BT\n\n"
                "Verifica el nombre e intenta de nuevo."
            ),
        )

    subject_text = extract_subject(text)
    subject = await find_subject(session, subject_text) if subject_text else None

    if not subject:
        return AgentResult(
            saved=False,
            waiting_for_subject=True,
            pending_grade_id=grade.id,
            pending_grade_name=grade.name,
            pending_delivery=extract_date(text),
            message=(
                f"Curso: *{grade.name}* ✓\n\n"
                "No identifiqué la *asignatura*. ¿Cuál es?\n\n"
                "Ejemplos: _Matemáticas_, _Física_, _Inglés_, _Historia_"
            ),
        )

    delivery = extract_date(text)
    return await _save(session, text, grade.id, grade.name, subject.id, subject.name, delivery)


async def save_with_subject(
    text: str,
    subject_text: str,
    grade_id: int,
    grade_name: str,
    delivery: date | None,
    session: AsyncSession,
) -> AgentResult:
    subject = await find_subject(session, subject_text)
    if not subject:
        return AgentResult(
            saved=False,
            waiting_for_subject=True,
            pending_grade_id=grade_id,
            pending_grade_name=grade_name,
            pending_delivery=delivery,
            message=(
                f"No reconocí la asignatura *{subject_text}*.\n\n"
                "Intenta con el nombre completo. Ejemplos:\n"
                "• _Matemáticas_, _Física_, _Química_, _Biología_\n"
                "• _Historia_, _Inglés_, _Lengua y Literatura_\n"
                "• _Educación Física_, _Filosofía_"
            ),
        )
    return await _save(session, text, grade_id, grade_name, subject.id, subject.name, delivery)


async def _save(
    session: AsyncSession,
    text: str,
    grade_id: int,
    grade_name: str,
    subject_id: int,
    subject_name: str,
    delivery: date | None,
) -> AgentResult:
    record = await save_homework(
        session,
        homework=text,
        grade_id=grade_id,
        subject_id=subject_id,
        delivery_date=delivery,
    )
    delivery_str = record.delivery_date.strftime("%d/%m/%Y") if record.delivery_date else "no especificada"
    return AgentResult(
        saved=True,
        homework_id=record.id,
        grade_name=grade_name,
        subject_name=subject_name,
        message=(
            f"Tarea registrada.\n"
            f"ID: {record.id} | Curso: *{grade_name}*\n"
            f"Asignatura: *{subject_name}*\n"
            f"Fecha de entrega: {delivery_str}"
        ),
    )
