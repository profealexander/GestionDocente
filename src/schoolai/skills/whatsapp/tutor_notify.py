"""Reporte diario de jornada al docente tutor + envío a representantes.

Flujo:
  _finish_jornada()
    → genera reporte por curso (inasistencias + tareas vencidas hoy)
    → muestra en Telegram al docente con botón [📤 Enviar a representantes]
    → docente aprueba
    → SchoolAI envía WhatsApp a cada representante del curso
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timezone

from loguru import logger
from sqlalchemy import select

from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.db.models.student import Student
from schoolai.db.models.attendance import Attendance
from schoolai.db.models.homework import Homework
from schoolai.db.models.homework_submission import HomeworkSubmission


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class StudentReport:
    name: str
    absent: bool = False
    late: bool = False
    justified: bool = False
    absent_subject: str = ""      # materia donde faltó
    missing_hw: list[str] = field(default_factory=list)  # nombres de materias


@dataclass
class GradeReport:
    grade_id: int
    grade_name: str
    students: dict[int, StudentReport] = field(default_factory=dict)  # student_id → report

    @property
    def has_issues(self) -> bool:
        return any(
            s.absent or s.late or s.justified or s.missing_hw
            for s in self.students.values()
        )


# ── Query principal ───────────────────────────────────────────────────────────

async def build_daily_reports(today: date) -> list[GradeReport]:
    """Construye reportes del día por curso combinando asistencia y tareas."""
    async with async_session() as session:
        reports: dict[int, GradeReport] = {}

        # 1. Inasistencias del día
        att_records = (
            (await session.execute(
                select(Attendance).where(
                    Attendance.date == today,
                    Attendance.status.in_(["absent", "late", "justified"]),
                )
            )).scalars().all()
        )

        for rec in att_records:
            student = await session.get(Student, rec.student_id)
            if not student or not student.person:
                continue
            grade_id = student.grade_id
            grade = await session.get(Grade, grade_id)
            if grade_id not in reports:
                reports[grade_id] = GradeReport(
                    grade_id=grade_id,
                    grade_name=grade.name if grade else f"Curso {grade_id}",
                )
            name = f"{student.person.first_name} {student.person.last_name}"
            sr = reports[grade_id].students.setdefault(rec.student_id, StudentReport(name=name))
            if rec.status == "absent":
                sr.absent = True
                sr.absent_subject = rec.subject_name or ""
            elif rec.status == "late":
                sr.late = True
                sr.absent_subject = rec.subject_name or ""
            elif rec.status == "justified":
                sr.justified = True
                sr.absent_subject = rec.subject_name or ""

        # 2. Tareas con entrega hoy que tienen no-entregas registradas
        hw_today = (
            (await session.execute(
                select(Homework).where(
                    Homework.is_open == False,  # noqa: E712
                )
            )).scalars().all()
        )
        # Filtrar las que vencían hoy
        hw_due_today = [
            hw for hw in hw_today
            if hw.delivery_date and hw.delivery_date.astimezone(timezone.utc).date() == today
        ]

        for hw in hw_due_today:
            missing = (
                (await session.execute(
                    select(HomeworkSubmission).where(
                        HomeworkSubmission.homework_id == hw.id,
                        HomeworkSubmission.status == "missing",
                    )
                )).scalars().all()
            )
            for sub in missing:
                student = await session.get(Student, sub.student_id)
                if not student or not student.person:
                    continue
                grade_id = student.grade_id
                grade = await session.get(Grade, grade_id)
                if grade_id not in reports:
                    reports[grade_id] = GradeReport(
                        grade_id=grade_id,
                        grade_name=grade.name if grade else f"Curso {grade_id}",
                    )
                name = f"{student.person.first_name} {student.person.last_name}"
                sr = reports[grade_id].students.setdefault(
                    sub.student_id, StudentReport(name=name),
                )
                subject_name = hw.subject.name if hw.subject else "Materia"
                sr.missing_hw.append(subject_name)

    return [r for r in reports.values() if r.has_issues]


# ── Formato del reporte para Telegram ────────────────────────────────────────

def format_telegram_report(report: GradeReport, today: date) -> str:
    lines = [
        f"📋 <b>Reporte de jornada — {report.grade_name}</b>",
        f"Fecha: {today.strftime('%d/%m/%Y')}",
        "",
    ]

    # Agrupar inasistencias por asignatura (docente)
    by_subject: dict[str, list[tuple[str, str]]] = {}  # subject → [(name, status)]
    for sr in report.students.values():
        if sr.absent or sr.late or sr.justified:
            subject = sr.absent_subject or "Sin asignatura"
            status = "❌ Falta" if sr.absent else "⏰ Atraso" if sr.late else "📄 Justificado"
            by_subject.setdefault(subject, []).append((sr.name, status))

    if by_subject:
        lines.append("👥 <b>Inasistencias por asignatura:</b>")
        for subject, students in sorted(by_subject.items()):
            lines.append(f"  <i>{subject}</i>")
            for name, status in students:
                lines.append(f"    • {name} — {status}")

    # Tareas no entregadas por asignatura
    by_hw: dict[str, list[str]] = {}  # subject → [student names]
    for sr in report.students.values():
        for subj in sr.missing_hw:
            by_hw.setdefault(subj, []).append(sr.name)

    if by_hw:
        lines.append("")
        lines.append("📚 <b>Tareas no entregadas por asignatura:</b>")
        for subject, students in sorted(by_hw.items()):
            lines.append(f"  <i>{subject}</i>")
            for name in students:
                lines.append(f"    • {name}")

    total = len(report.students)
    lines += ["", f"Total de estudiantes con novedades: <b>{total}</b>"]
    return "\n".join(lines)


# ── Envío WhatsApp a representantes ──────────────────────────────────────────

async def send_report_to_representatives(grade_id: int, today: date) -> tuple[int, int]:
    """Envía WhatsApp a representantes del curso. Retorna (enviados, fallidos)."""
    from schoolai.config import settings
    from schoolai.skills.whatsapp.sender import send_whatsapp
    from schoolai.db.models.whatsapp_contact import WhatsAppContact
    from schoolai.db.models.student_representative import StudentRepresentative

    if not settings.green_api_instance or not settings.green_api_token:
        logger.warning("[tutor_notify] Green API no configurada")
        return 0, 0

    reports = await build_daily_reports(today)
    report = next((r for r in reports if r.grade_id == grade_id), None)
    if not report:
        return 0, 0

    sent = failed = 0

    async with async_session() as session:
        for student_id, sr in report.students.items():
            # Buscar representante primario con WhatsApp
            rep_link = (
                await session.execute(
                    select(StudentRepresentative).where(
                        StudentRepresentative.student_id == student_id,
                        StudentRepresentative.is_primary_notify == True,  # noqa: E712
                        StudentRepresentative.status == "active",
                    )
                )
            ).scalar_one_or_none()

            if not rep_link:
                continue

            contacts = (
                (await session.execute(
                    select(WhatsAppContact).where(
                        WhatsAppContact.person_id == rep_link.person_id,
                        WhatsAppContact.status == "active",
                    )
                )).scalars().all()
            )
            if not contacts:
                continue

            message = _build_rep_message(sr, report.grade_name, today)
            ok = await send_whatsapp(
                settings.green_api_instance,
                settings.green_api_token,
                contacts[0].phone,
                message,
            )
            if ok:
                sent += 1
            else:
                failed += 1

    logger.info(f"[tutor_notify] grade={grade_id} rep_sent={sent} failed={failed}")
    return sent, failed


def _build_rep_message(sr: StudentReport, grade_name: str, today: date) -> str:
    date_str = today.strftime("%d/%m/%Y")
    lines = [f"Estimado/a representante de {sr.name} ({grade_name}) — {date_str}", ""]

    if sr.absent:
        lines.append("• No asistió a clases hoy.")
    if sr.late:
        lines.append("• Llegó tarde a clases.")
    if sr.justified:
        lines.append("• Asistencia justificada.")
    if sr.missing_hw:
        materias = ", ".join(sr.missing_hw)
        lines.append(f"• No entregó tarea de: {materias}.")

    lines += ["", "— SchoolAI"]
    return "\n".join(lines)
