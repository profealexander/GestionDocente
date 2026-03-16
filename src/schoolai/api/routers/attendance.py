"""Attendance endpoints — read-only attendance records."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.auth import get_current_user
from schoolai.api.schemas import AttendanceOut
from schoolai.db.connection import get_session
from schoolai.db.models.attendance import Attendance
from schoolai.db.models.student import Student

router = APIRouter(
    prefix="/attendance",
    tags=["Attendance"],
    dependencies=[Depends(get_current_user)],
)

_STATUS_LABELS = {"F": "absent", "AT": "late", "J": "justified"}


@router.get(
    "/",
    response_model=list[AttendanceOut],
    summary="List attendance records",
    description=(
        "Returns attendance records filtered by grade, student, date range, or status. "
        "Status values: F = absent, AT = late, J = justified."
    ),
)
async def list_attendance(
    grade_id: Optional[int] = Query(None, description="Filter by grade ID"),
    student_id: Optional[int] = Query(None, description="Filter by student ID"),
    date_from: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by status: F | AT | J"),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Attendance).order_by(Attendance.date.desc(), Attendance.student_id)

    if student_id is not None:
        stmt = stmt.where(Attendance.student_id == student_id)
    if date_from is not None:
        stmt = stmt.where(Attendance.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Attendance.date <= date_to)
    if status is not None:
        stmt = stmt.where(Attendance.status == status)

    if grade_id is not None:
        # Join through students to filter by grade
        student_ids_stmt = select(Student.id).where(Student.grade_id == grade_id)
        student_ids = (await session.execute(student_ids_stmt)).scalars().all()
        stmt = stmt.where(Attendance.student_id.in_(student_ids))

    rows = (await session.execute(stmt)).scalars().all()

    # Batch-load all referenced students in one query (avoids N+1)
    student_ids = list({r.student_id for r in rows if r.student_id})
    students_by_id: dict[int, Student] = {}
    if student_ids:
        s_stmt = select(Student).where(Student.id.in_(student_ids))
        students_by_id = {
            s.id: s
            for s in (await session.execute(s_stmt)).unique().scalars().all()
        }

    def _to_out(att: Attendance) -> AttendanceOut:
        s = students_by_id.get(att.student_id)  # type: ignore[arg-type]
        return AttendanceOut(
            id=att.id,
            student_id=att.student_id,
            student_name=s.person.full_name() if s and s.person else None,
            grade_id=s.grade_id if s else None,
            date=att.date,
            status=att.status,
            notes=att.notes,
        )

    return [_to_out(r) for r in rows]
