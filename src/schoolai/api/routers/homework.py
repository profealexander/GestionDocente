"""Homework endpoints — list and manage homework assignments."""

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.auth import get_current_user
from schoolai.api.schemas import HomeworkClose, HomeworkOut, MessageOut
from schoolai.db.connection import get_session
from schoolai.db.models.homework import Homework
from schoolai.db.models.homework_submission import HomeworkSubmission


class HomeworkCreate(BaseModel):
    description: str
    grade_id: int
    subject_id: Optional[int] = None
    delivery_date: Optional[datetime.date] = None


class ReportRecord(BaseModel):
    student_id: int
    status: str  # "missing" | "delivered"


class SubmissionOut(BaseModel):
    student_id: int
    status: str


router = APIRouter(
    prefix="/homework",
    tags=["Homework"],
    dependencies=[Depends(get_current_user)],
)


def _to_out(hw: Homework) -> HomeworkOut:
    return HomeworkOut(
        id=hw.id,
        description=hw.homework,
        grade_id=hw.grade_id,
        grade_name=hw.grade.name if hw.grade else "",
        subject_id=hw.subject_id,
        subject_name=hw.subject.name if hw.subject else None,
        sequence_num=hw.sequence_num,
        trimester_num=hw.trimester_num,
        submission_date=hw.submission_date,
        delivery_date=hw.delivery_date,
        is_open=hw.is_open,
    )


@router.post(
    "/",
    response_model=HomeworkOut,
    summary="Create homework assignment",
)
async def create_homework(
    body: HomeworkCreate,
    session: AsyncSession = Depends(get_session),
):
    from schoolai.skills.homework.repository import save_homework

    hw = await save_homework(
        session,
        homework=body.description,
        grade_id=body.grade_id,
        subject_id=body.subject_id,
        delivery_date=body.delivery_date,
    )
    return _to_out(hw)


@router.get(
    "/",
    response_model=list[HomeworkOut],
    summary="List homework assignments",
    description=(
        "Returns homework assignments. Filter by grade, subject, or open status. "
        "Ordered by submission date descending."
    ),
)
async def list_homework(
    grade_id: Optional[int] = Query(None, description="Filter by grade ID"),
    subject_id: Optional[int] = Query(None, description="Filter by subject ID"),
    is_open: Optional[bool] = Query(None, description="Filter by open status"),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Homework).order_by(Homework.submission_date.desc())
    if grade_id is not None:
        stmt = stmt.where(Homework.grade_id == grade_id)
    if subject_id is not None:
        stmt = stmt.where(Homework.subject_id == subject_id)
    if is_open is not None:
        stmt = stmt.where(Homework.is_open == is_open)
    result = await session.execute(stmt)
    return [_to_out(hw) for hw in result.scalars().all()]


@router.get(
    "/{homework_id}",
    response_model=HomeworkOut,
    summary="Get homework by ID",
    description="Returns a single homework assignment by its ID.",
)
async def get_homework(
    homework_id: int,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Homework).where(Homework.id == homework_id))
    hw = result.scalars().first()
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")
    return _to_out(hw)


@router.put(
    "/{homework_id}",
    response_model=MessageOut,
    summary="Update homework (close/open)",
)
@router.patch(
    "/{homework_id}",
    response_model=MessageOut,
    summary="Close a homework assignment",
    description="Marks a homework as closed (is_open = false).",
)
async def close_homework(
    homework_id: int,
    body: HomeworkClose,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Homework).where(Homework.id == homework_id))
    hw = result.scalars().first()
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")
    hw.is_open = body.is_open
    await session.commit()
    status = "abierta" if body.is_open else "cerrada"
    return MessageOut(message=f"Tarea {homework_id} marcada como {status}.")


@router.get(
    "/{homework_id}/submissions",
    response_model=list[SubmissionOut],
    summary="Get submission statuses for a homework",
)
async def get_submissions(
    homework_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Returns all recorded submission statuses for a homework assignment."""
    rows = (
        await session.execute(
            select(HomeworkSubmission).where(HomeworkSubmission.homework_id == homework_id)
        )
    ).scalars().all()
    return [SubmissionOut(student_id=r.student_id, status=r.status) for r in rows]


@router.post(
    "/{homework_id}/report",
    response_model=MessageOut,
    summary="Bulk upsert homework submission statuses",
)
async def report_homework(
    homework_id: int,
    records: list[ReportRecord],
    session: AsyncSession = Depends(get_session),
):
    """Inserts or updates submission statuses for a list of students."""
    if not records:
        return MessageOut(message="Sin registros.")

    hw = (await session.execute(select(Homework).where(Homework.id == homework_id))).scalars().first()
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")

    values = [
        {"homework_id": homework_id, "student_id": r.student_id, "status": r.status}
        for r in records
    ]
    stmt = (
        insert(HomeworkSubmission)
        .values(values)
        .on_conflict_do_update(
            index_elements=["homework_id", "student_id"],
            set_={"status": insert(HomeworkSubmission).excluded.status},
        )
    )
    await session.execute(stmt)
    await session.commit()
    return MessageOut(message=f"{len(records)} registros guardados.")
