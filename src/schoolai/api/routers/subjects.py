"""Subject endpoints — read-only catalog of academic subjects."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.api.schemas import SubjectOut
from schoolai.db.connection import get_session
from schoolai.db.models.subject import Subject

# Public endpoint — no auth required (catalog data needed by SvelteKit before login)
router = APIRouter(prefix="/subjects", tags=["Subjects"])


@router.get(
    "/",
    response_model=list[SubjectOut],
    summary="List subjects",
    description="Returns subjects optionally filtered by education level (basica or bachillerato).",
)
async def list_subjects(
    sublevel: Optional[str] = Query(None, description="Filter by level: basica or bachillerato"),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Subject).order_by(Subject.sublevel, Subject.area, Subject.name)
    if sublevel:
        stmt = stmt.where(Subject.sublevel == sublevel)
    result = await session.execute(stmt)
    return result.scalars().all()
