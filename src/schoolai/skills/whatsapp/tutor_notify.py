"""Reporte diario de jornada al docente tutor + envío a representantes.

Flujo:
  _finish_jornada()
    → genera reporte por curso (inasistencias + tareas vencidas hoy)
    → muestra en Telegram al docente con botón [📤 Enviar a representantes]
    → docente aprueba
    → SchoolAI envía WhatsApp a cada representante del curso
"""

from __future__ import annotations

import time
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
from schoolai.db.models.teacher import Teacher, TeacherPosition

# ── Cache para build_daily_reports ────────────────────────────────────────────
# Evita repetir la query costosa cuando la función se llama varias veces en la
# misma jornada (ej: generar tarjetas + envío por curso tras aprobación del tutor).
_REPORTS_CACHE: dict[date, tuple[list, float]] = {}  # date → (reports, expires_at)
_REPORTS_CACHE_TTL = 300  # 5 minutos


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
    """Construye reportes del día por curso combinando asistencia y tareas.

    Resultado cacheado 5 minutos para que múltiples llamadas en la misma jornada
    (generar tarjetas + envíos por curso) no repitan la query costosa.
    """
    cached = _REPORTS_CACHE.get(today)
    if cached and time.monotonic() < cached[1]:
        return cached[0]

    async with async_session() as session:
        reports: dict[int, GradeReport] = {}

        # 1. Inasistencias del día — carga masiva de students y grades
        att_records = (
            (await session.execute(
                select(Attendance).where(
                    Attendance.date == today,
                    Attendance.status.in_(["absent", "late", "justified"]),
                )
            )).scalars().all()
        )

        if att_records:
            student_ids = list({r.student_id for r in att_records})
            students_map: dict[int, Student] = {
                s.id: s
                for s in (
                    await session.execute(
                        select(Student).where(Student.id.in_(student_ids))
                    )
                ).scalars().all()
            }

            grade_ids = {s.grade_id for s in students_map.values() if s.grade_id}
            grades_map: dict[int, Grade] = {
                g.id: g
                for g in (
                    await session.execute(
                        select(Grade).where(Grade.id.in_(grade_ids))
                    )
                ).scalars().all()
            }

            for rec in att_records:
                student = students_map.get(rec.student_id)
                if not student or not student.person:
                    continue
                grade_id = student.grade_id
                if not grade_id:
                    continue
                grade = grades_map.get(grade_id)
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
        hw_due_today = [
            hw for hw in (
                await session.execute(
                    select(Homework).where(
                        Homework.is_open.is_(False),
                        Homework.delivery_date.isnot(None),
                    )
                )
            ).scalars().all()
            if hw.delivery_date and hw.delivery_date.astimezone(timezone.utc).date() == today
        ]

        if hw_due_today:
            hw_ids = [hw.id for hw in hw_due_today]
            missing_subs = (
                await session.execute(
                    select(HomeworkSubmission).where(
                        HomeworkSubmission.homework_id.in_(hw_ids),
                        HomeworkSubmission.status == "missing",
                    )
                )
            ).scalars().all()

            # Cargar todos los students involucrados de una vez
            sub_student_ids = list({s.student_id for s in missing_subs})
            if sub_student_ids:
                sub_students_map: dict[int, Student] = {
                    s.id: s
                    for s in (
                        await session.execute(
                            select(Student).where(Student.id.in_(sub_student_ids))
                        )
                    ).scalars().all()
                }

                # Cargar grades que falten
                new_grade_ids = {
                    s.grade_id
                    for s in sub_students_map.values()
                    if s.grade_id and s.grade_id not in reports
                }
                if new_grade_ids:
                    new_grades = (
                        await session.execute(
                            select(Grade).where(Grade.id.in_(new_grade_ids))
                        )
                    ).scalars().all()
                    extra_grades_map = {g.id: g for g in new_grades}
                else:
                    extra_grades_map = {}

                hw_by_id = {hw.id: hw for hw in hw_due_today}

                for sub in missing_subs:
                    student = sub_students_map.get(sub.student_id)
                    if not student or not student.person:
                        continue
                    grade_id = student.grade_id
                    if not grade_id:
                        continue
                    if grade_id not in reports:
                        grade = extra_grades_map.get(grade_id)
                        reports[grade_id] = GradeReport(
                            grade_id=grade_id,
                            grade_name=grade.name if grade else f"Curso {grade_id}",
                        )
                    name = f"{student.person.first_name} {student.person.last_name}"
                    sr = reports[grade_id].students.setdefault(
                        sub.student_id, StudentReport(name=name),
                    )
                    hw = hw_by_id.get(sub.homework_id)
                    subject_name = hw.subject.name if hw and hw.subject else "Materia"
                    sr.missing_hw.append(subject_name)

    result = [r for r in reports.values() if r.has_issues]
    _REPORTS_CACHE[today] = (result, time.monotonic() + _REPORTS_CACHE_TTL)
    return result


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
    student_ids = list(report.students.keys())

    async with async_session() as session:
        # Carga masiva de representantes primarios con notificación activa
        rep_links = (
            await session.execute(
                select(StudentRepresentative).where(
                    StudentRepresentative.student_id.in_(student_ids),
                    StudentRepresentative.is_primary_notify.is_(True),
                    StudentRepresentative.status == "active",
                )
            )
        ).scalars().all()

        rep_by_student: dict[int, StudentRepresentative] = {
            r.student_id: r for r in rep_links
        }

        # Carga masiva de contactos WhatsApp para los representantes encontrados
        person_ids = list({r.person_id for r in rep_links})
        if not person_ids:
            return 0, 0

        contacts_all = (
            await session.execute(
                select(WhatsAppContact).where(
                    WhatsAppContact.person_id.in_(person_ids),
                    WhatsAppContact.status == "active",
                )
            )
        ).scalars().all()

        contacts_by_person: dict[int, WhatsAppContact] = {}
        for c in contacts_all:
            contacts_by_person.setdefault(c.person_id, c)

    for student_id, sr in report.students.items():
        rep_link = rep_by_student.get(student_id)
        if not rep_link:
            continue
        contact = contacts_by_person.get(rep_link.person_id)
        if not contact:
            continue

        message = _build_rep_message(sr, report.grade_name, today)
        ok = await send_whatsapp(
            settings.green_api_instance,
            settings.green_api_token,
            contact.phone,
            message,
        )
        if ok:
            sent += 1
        else:
            failed += 1

    logger.info(f"[tutor_notify] grade={grade_id} rep_sent={sent} failed={failed}")
    return sent, failed


async def get_tutor_grade_ids(teacher_id: int) -> list[int]:
    """Grade IDs para los que este docente es tutor activo."""
    async with async_session() as session:
        rows = (await session.execute(
            select(TeacherPosition).where(
                TeacherPosition.teacher_id == teacher_id,
                TeacherPosition.position_type == "tutor",
                TeacherPosition.grade_id.isnot(None),
                TeacherPosition.is_active.is_(True),
            )
        )).scalars().all()
        return [r.grade_id for r in rows]


async def get_inspector_telegram_ids() -> list[int]:
    """Telegram IDs de todos los inspectores activos."""
    async with async_session() as session:
        positions = (await session.execute(
            select(TeacherPosition).where(
                TeacherPosition.position_type == "cargo",
                TeacherPosition.detail == "inspector",
                TeacherPosition.is_active.is_(True),
            )
        )).scalars().all()
        if not positions:
            return []
        teacher_ids = [p.teacher_id for p in positions]
        teachers = (await session.execute(
            select(Teacher).where(
                Teacher.id.in_(teacher_ids),
                Teacher.telegram_id.isnot(None),
                Teacher.is_active.is_(True),
            )
        )).scalars().all()
        return [t.telegram_id for t in teachers]


async def notify_inspector_tutor_absent(
    bot,
    teacher_id: int,
    reason_label: str,
    today: date,
) -> None:
    """Envía al inspector el reporte del curso tutorado cuando el tutor está ausente."""
    tutor_grade_ids = await get_tutor_grade_ids(teacher_id)
    if not tutor_grade_ids:
        return

    inspector_ids = await get_inspector_telegram_ids()
    if not inspector_ids:
        logger.warning("[tutor_notify] tutor ausente pero no hay inspectores con telegram_id")
        return

    # Nombre del tutor
    async with async_session() as session:
        teacher = await session.get(Teacher, teacher_id)
        tutor_name = (
            f"{teacher.person.first_name} {teacher.person.last_name}"
            if teacher and teacher.person
            else f"Docente #{teacher_id}"
        )

        # Nombres de los cursos tutorados
        grade_names: dict[int, str] = {}
        if tutor_grade_ids:
            grades = (await session.execute(
                select(Grade).where(Grade.id.in_(tutor_grade_ids))
            )).scalars().all()
            grade_names = {g.id: g.name for g in grades}

    # Reporte de estudiantes del día
    all_reports = await build_daily_reports(today)
    reports_by_grade = {r.grade_id: r for r in all_reports}

    from telegram.constants import ParseMode

    for grade_id in tutor_grade_ids:
        grade_name = grade_names.get(grade_id, f"Curso {grade_id}")
        report = reports_by_grade.get(grade_id)

        lines = [
            "⚠️ <b>AVISO — Tutor ausente</b>",
            f"Curso: <b>{grade_name}</b>",
            f"Tutor: <b>{tutor_name}</b>",
            f"Motivo: {reason_label}",
            f"Fecha: {today.strftime('%d/%m/%Y')}",
            "",
        ]
        if report and report.has_issues:
            lines.append(format_telegram_report(report, today))
        else:
            lines.append("Sin novedades de estudiantes registradas hoy.")

        text = "\n".join(lines)
        for inspector_id in inspector_ids:
            try:
                await bot.send_message(
                    chat_id=inspector_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
                logger.info(
                    f"[tutor_notify] inspector={inspector_id} notificado "
                    f"tutor={teacher_id} grade={grade_id}",
                )
            except Exception as e:
                logger.warning(
                    f"[tutor_notify] no se pudo notificar inspector={inspector_id}: {e}",
                )


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
