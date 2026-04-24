"""Grade endpoints — read-only catalog of school grades."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.schemas import GradeOut
from schoolai.db.connection import get_session
from schoolai.db.models.grade import Grade

router = APIRouter(prefix="/grades", tags=["Grades"])


@router.get(
    "/",
    response_model=list[GradeOut],
    summary="List all grades",
    description="Returns all school grades ordered by level.",
)
async def list_grades(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Grade).order_by(Grade.sort_order))
    return result.scalars().all()
