"""CRUD operations for teacher positions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from schoolai.db.models.subject import Subject
from schoolai.db.models.teacher import Teacher, TeacherPosition


async def get_teacher_with_positions(
    session: AsyncSession,
    *,
    person_id: int | None = None,
    teacher_id: int | None = None,
) -> tuple[Teacher | None, list[TeacherPosition]]:
    """Load teacher + active positions. Pass either person_id or teacher_id."""
    if person_id is not None:
        condition = Teacher.person_id == person_id
    elif teacher_id is not None:
        condition = Teacher.id == teacher_id
    else:
        raise ValueError("Must pass person_id or teacher_id")

    stmt = (
        select(Teacher)
        .where(condition)
        .options(selectinload(Teacher.positions))
    )
    teacher = (await session.execute(stmt)).scalars().first()
    if not teacher:
        return None, []

    positions = [p for p in teacher.positions if p.is_active]
    return teacher, positions


async def add_position(
    session: AsyncSession,
    *,
    teacher_id: int,
    position_type: str,
    grade_id: int | None = None,
    subnivel: str | None = None,
    area: str | None = None,
    detail: str | None = None,
) -> TeacherPosition:
    pos = TeacherPosition(
        teacher_id=teacher_id,
        position_type=position_type,
        grade_id=grade_id,
        subnivel=subnivel,
        area=area,
        detail=detail,
    )
    session.add(pos)
    await session.commit()
    await session.refresh(pos)
    return pos


async def deactivate_position(session: AsyncSession, position_id: int) -> bool:
    stmt = select(TeacherPosition).where(TeacherPosition.id == position_id)
    pos = (await session.execute(stmt)).scalars().first()
    if pos:
        pos.is_active = False
        await session.commit()
        return True
    return False


async def get_areas(session: AsyncSession) -> list[str]:
    """Distinct area values from subjects table, sorted."""
    stmt = select(Subject.area).distinct().order_by(Subject.area)
    return list((await session.execute(stmt)).scalars().all())


async def get_admin_cargo(session: AsyncSession, telegram_id: int) -> str | None:
    """Return the cargo detail if this teacher has an active institutional cargo, else None."""
    stmt = (
        select(Teacher)
        .where(Teacher.telegram_id == telegram_id, Teacher.is_active.is_(True))
        .options(selectinload(Teacher.positions))
    )
    teacher = (await session.execute(stmt)).scalars().first()
    if not teacher:
        return None
    for p in teacher.positions:
        if p.position_type == "cargo" and p.is_active and p.detail:
            return p.detail
    return None
