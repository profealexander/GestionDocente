"""Repository functions for teachers and schedules."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.person import Person
from schoolai.db.models.teacher import Schedule, Teacher


async def get_teacher_by_telegram(session: AsyncSession, telegram_id: int) -> Teacher | None:
    stmt = select(Teacher).where(Teacher.telegram_id == telegram_id, Teacher.is_active.is_(True))
    return (await session.execute(stmt)).scalars().first()


async def get_docentes(session: AsyncSession) -> list[Person]:
    """Returns all people with role=docente."""
    stmt = select(Person).where(Person.role == "teacher", Person.status == "active").order_by(Person.last_name)
    return (await session.execute(stmt)).unique().scalars().all()


async def get_or_create_teacher(session: AsyncSession, person_id: int, telegram_id: int) -> Teacher:
    stmt = select(Teacher).where(Teacher.person_id == person_id)
    teacher = (await session.execute(stmt)).scalars().first()
    if teacher:
        teacher.telegram_id = telegram_id
    else:
        teacher = Teacher(person_id=person_id, telegram_id=telegram_id)
        session.add(teacher)
    await session.commit()
    await session.refresh(teacher)
    return teacher


async def save_schedule_periods(
    session: AsyncSession,
    teacher_id: int,
    day_of_week: int,
    periods: list[dict],
) -> int:
    """Upsert schedule periods for a teacher on a given day.
    Replaces existing periods for that day before inserting new ones.
    Returns count of saved periods."""
    # Bulk delete existing periods for this teacher+day
    await session.execute(
        delete(Schedule).where(
            Schedule.teacher_id == teacher_id,
            Schedule.day_of_week == day_of_week,
        )
    )

    # Bulk insert new periods
    session.add_all([
        Schedule(
            teacher_id=teacher_id,
            day_of_week=day_of_week,
            period_num=p["period_num"],
            start_time=p["start_time"],
            end_time=p["end_time"],
            grade_id=p["grade_id"],
            subject_id=p["subject_id"],
        )
        for p in periods
    ])

    await session.commit()
    return len(periods)


async def get_schedule_for_day(
    session: AsyncSession,
    teacher_id: int,
    day_of_week: int,
) -> list[Schedule]:
    stmt = (
        select(Schedule)
        .where(
            Schedule.teacher_id == teacher_id,
            Schedule.day_of_week == day_of_week,
            Schedule.is_active.is_(True),
        )
        .order_by(Schedule.period_num)
    )
    return (await session.execute(stmt)).scalars().all()
