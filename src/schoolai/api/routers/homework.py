"""Homework endpoints — list and manage homework assignments."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.auth import get_current_user
from schoolai.api.schemas import HomeworkClose, HomeworkOut, MessageOut
from schoolai.db.connection import get_session
from schoolai.db.models.homework import Homework

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
