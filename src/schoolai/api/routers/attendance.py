"""Attendance endpoints."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.auth import get_current_user
from schoolai.api.schemas import AttendanceOut, MessageOut
from schoolai.db.connection import get_session
from schoolai.db.models.attendance import Attendance
from schoolai.db.models.student import Student

_STATUS_MAP = {"absent": "F", "late": "AT", "justified": "J"}


class AttendanceRecordIn(BaseModel):
    student_id: int
    status: str  # present | absent | late | justified


class AttendanceSaveIn(BaseModel):
    grade_id: int
    date: date
    records: list[AttendanceRecordIn]


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
        stmt = stmt.join(Student, Attendance.student_id == Student.id).where(
            Student.grade_id == grade_id
        )

    rows = (await session.execute(stmt)).scalars().all()

    # Batch-load all referenced students in one query (avoids N+1)
    student_ids = list({r.student_id for r in rows if r.student_id})
    students_by_id: dict[int, Student] = {}
    if student_ids:
        s_stmt = select(Student).where(Student.id.in_(student_ids))
        students_by_id = {s.id: s for s in (await session.execute(s_stmt)).unique().scalars().all()}

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


@router.post(
    "/",
    response_model=MessageOut,
    summary="Save attendance batch",
    description=(
        "Upsert attendance for a full grade on a given date. "
        "Only absent/late/justified are stored."
    ),
)
async def save_attendance(
    body: AttendanceSaveIn,
    session: AsyncSession = Depends(get_session),
):
    # Get all student ids in this grade
    student_ids_in_grade = (
        (await session.execute(select(Student.id).where(Student.grade_id == body.grade_id)))
        .scalars()
        .all()
    )

    # Delete existing records for this grade+date
    await session.execute(
        delete(Attendance).where(
            Attendance.student_id.in_(student_ids_in_grade),
            Attendance.date == body.date,
        ),
    )

    # Validate all submitted student_ids belong to the grade
    valid_ids = set(student_ids_in_grade)
    invalid = [r.student_id for r in body.records if r.student_id not in valid_ids]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"student_id fuera del grado {body.grade_id}: {invalid}",
        )

    # Insert only non-present records
    inserted = 0
    for rec in body.records:
        db_status = _STATUS_MAP.get(rec.status)
        if db_status is None:
            continue  # skip "present"
        session.add(Attendance(student_id=rec.student_id, date=body.date, status=db_status))
        inserted += 1

    await session.commit()
    return MessageOut(message=f"Asistencia guardada: {inserted} registros para {body.date}.")
