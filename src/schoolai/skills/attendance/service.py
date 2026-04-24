"""Save absence records to the attendance table."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.attendance import Attendance
from schoolai.skills.attendance.constants import ABSENT

_ECUADOR_TZ = timezone(timedelta(hours=-5))


async def infer_period_from_schedule(
    session: AsyncSession,
    teacher_id: int,
    grade_id: int,
) -> tuple[str | None, str | None, str | None]:
    """Infiere materia y hora del período actual comparando con el horario del docente.

    Returns: (subject_name, start_time, end_time) o (None, None, None) si no hay coincidencia.
    """
    from schoolai.db.models.teacher import Schedule

    now = datetime.now(tz=_ECUADOR_TZ)
    day_of_week = now.weekday()          # 0=Lun … 4=Vie
    current_time = now.strftime("%H:%M")

    schedules = (
        await session.execute(
            select(Schedule).where(
                Schedule.teacher_id == teacher_id,
                Schedule.grade_id == grade_id,
                Schedule.day_of_week == day_of_week,
                Schedule.is_active.is_(True),
            )
        )
    ).scalars().all()

    for s in schedules:
        if s.start_time <= current_time <= s.end_time:
            return s.subject.name, s.start_time, s.end_time

    return None, None, None


@dataclass
class AttendanceResult:
    saved: int
    date: date
    grade_name: str


async def save_absences(
    student_ids: list[int],
    statuses: dict[int, str],  # student_id → 'F' | 'AT' | 'J'
    attendance_date: date,
    session: AsyncSession,
    subject_name: str | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
) -> AttendanceResult:
    """Insert absence/late records. Idempotent: removes existing records for same day+subject first.

    When subject_name is provided (jornada mode), only deletes/inserts records for that subject,
    allowing multiple subject-level records per student per day.
    When subject_name is None, deletes all records with null subject (legacy "day-level" records).
    """
    if not student_ids:
        return AttendanceResult(saved=0, date=attendance_date, grade_name="")

    # Scoped delete: by subject when provided, otherwise null-subject records only
    if subject_name:
        await session.execute(
            delete(Attendance).where(
                Attendance.student_id.in_(student_ids),
                Attendance.date == attendance_date,
                Attendance.subject_name == subject_name,
            ),
        )
    else:
        await session.execute(
            delete(Attendance).where(
                Attendance.student_id.in_(student_ids),
                Attendance.date == attendance_date,
                Attendance.subject_name.is_(None),
            ),
        )

    await session.execute(
        insert(Attendance),
        [
            {
                "student_id": sid,
                "date": attendance_date,
                "status": statuses.get(sid, ABSENT),
                "subject_name": subject_name,
                "period_start": period_start,
                "period_end": period_end,
            }
            for sid in student_ids
        ],
    )

    await session.commit()
    return AttendanceResult(saved=len(student_ids), date=attendance_date, grade_name="")
