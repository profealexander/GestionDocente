"""Student endpoints — read-only student roster."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.auth import get_current_user
from schoolai.api.schemas import StudentOut
from schoolai.db.connection import get_session
from schoolai.db.models.student import Student

router = APIRouter(
    prefix="/students",
    tags=["Students"],
    dependencies=[Depends(get_current_user)],
)


def _to_out(s: Student) -> StudentOut:
    full_name = s.person.full_name() if s.person else "—"
    return StudentOut(
        id=s.id,
        full_name=full_name,
        grade_id=s.grade_id,
        grade_name=s.grade.name if s.grade else "",
        section=s.section,
        status=s.status,
    )


@router.get(
    "/",
    response_model=list[StudentOut],
    summary="List students",
    description="Returns students optionally filtered by grade or status. Ordered by grade and name.",
)
async def list_students(
    grade_id: Optional[int] = Query(None, description="Filter by grade ID"),
    status: Optional[str] = Query("active", description="Filter by status: active | inactive"),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Student).order_by(Student.grade_id, Student.id)
    if grade_id is not None:
        stmt = stmt.where(Student.grade_id == grade_id)
    if status:
        stmt = stmt.where(Student.status == status)
    result = await session.execute(stmt)
    return [_to_out(s) for s in result.unique().scalars().all()]


@router.get(
    "/{student_id}",
    response_model=StudentOut,
    summary="Get student by ID",
    description="Returns a single student by their ID.",
)
async def get_student(
    student_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Student).where(Student.id == student_id))
    s = result.unique().scalars().first()
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    return _to_out(s)
