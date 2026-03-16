"""Save absence records to the attendance table."""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.attendance import Attendance
from schoolai.skills.attendance.constants import ABSENT


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
) -> AttendanceResult:
    """Insert absence/late records. Idempotent: removes existing records for same day first."""
    if not student_ids:
        return AttendanceResult(saved=0, date=attendance_date, grade_name="")

    # Remove existing records for these students on this date (re-take)
    await session.execute(
        delete(Attendance).where(
            Attendance.student_id.in_(student_ids),
            Attendance.date == attendance_date,
        )
    )

    for sid in student_ids:
        session.add(Attendance(
            student_id=sid,
            date=attendance_date,
            status=statuses.get(sid, ABSENT),
        ))

    await session.commit()
    return AttendanceResult(saved=len(student_ids), date=attendance_date, grade_name="")
