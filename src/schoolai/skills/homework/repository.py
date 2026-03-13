from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.grade import Grade
from schoolai.db.models.homework import Homework
from schoolai.db.models.subject import Subject


_GRADE_ALIASES = {
    # Primero BT
    "1bt": "PRIMERO BT", "1 bt": "PRIMERO BT", "1bachi": "PRIMERO BT",
    "1bachillerato": "PRIMERO BT", "1ero bt": "PRIMERO BT", "1ro bt": "PRIMERO BT",
    "1er bt": "PRIMERO BT", "1° bt": "PRIMERO BT", "1o bt": "PRIMERO BT",
    "primer bt": "PRIMERO BT", "primero bt": "PRIMERO BT", "primero bachillerato": "PRIMERO BT",
    # Segundo BT
    "2bt": "SEGUNDO BT", "2 bt": "SEGUNDO BT", "2bachi": "SEGUNDO BT",
    "2bachillerato": "SEGUNDO BT", "2do bt": "SEGUNDO BT", "2dobt": "SEGUNDO BT",
    "2° bt": "SEGUNDO BT", "2da bt": "SEGUNDO BT", "2da bt": "SEGUNDO BT",
    "segundo bt": "SEGUNDO BT", "segunda bt": "SEGUNDO BT",
    "segundo bachillerato": "SEGUNDO BT", "segunda bachillerato": "SEGUNDO BT",
    # Tercero BT
    "3bt": "TERCERO BT", "3 bt": "TERCERO BT", "3bachi": "TERCERO BT",
    "3bachillerato": "TERCERO BT", "3ero bt": "TERCERO BT", "3° bt": "TERCERO BT",
    "tercero bt": "TERCERO BT", "tercero bachillerato": "TERCERO BT",
    # EGB
    "2do egb": "SEGUNDO EGB", "2° egb": "SEGUNDO EGB", "segundo egb": "SEGUNDO EGB",
    "3ero egb": "TERCERO EGB", "3° egb": "TERCERO EGB", "tercero egb": "TERCERO EGB",
    "4to egb": "CUARTO EGB", "cuarto egb": "CUARTO EGB",
    "5to egb": "QUINTO EGB", "quinto egb": "QUINTO EGB",
    "6to egb": "SEXTO EGB", "sexto egb": "SEXTO EGB",
    "7mo egb": "SEPTIMO EGB", "séptimo egb": "SEPTIMO EGB", "septimo egb": "SEPTIMO EGB",
    "8vo egb": "OCTAVO EGB", "octavo egb": "OCTAVO EGB",
    "9no egb": "NOVENO EGB", "noveno egb": "NOVENO EGB",
    "10mo egb": "DECIMO EGB", "décimo egb": "DECIMO EGB", "decimo egb": "DECIMO EGB",
}


async def find_grade(session: AsyncSession, name: str) -> Grade | None:
    normalized = _GRADE_ALIASES.get(name.lower().strip())
    search = normalized or name.upper()
    result = await session.execute(
        select(Grade).where(Grade.name.ilike(f"%{search}%")).order_by(Grade.sort_order)
    )
    return result.scalars().first()


async def find_subject(session: AsyncSession, name: str) -> Subject | None:
    """Fuzzy search using pg_trgm similarity."""
    result = await session.execute(
        select(Subject)
        .where(func.similarity(func.lower(Subject.name), name.lower()) > 0.15)
        .order_by(func.similarity(func.lower(Subject.name), name.lower()).desc())
        .limit(1)
    )
    return result.scalars().first()


async def save_homework(
    session: AsyncSession,
    homework: str,
    grade_id: int,
    subject_id: int | None = None,
    delivery_date: date | None = None,
) -> Homework:
    record = Homework(
        homework=homework,
        grade_id=grade_id,
        subject_id=subject_id,
        delivery_date=delivery_date,
        is_open=True,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def list_open(session: AsyncSession, grade_id: int | None = None) -> list[Homework]:
    stmt = select(Homework).where(Homework.is_open.is_(True))
    if grade_id:
        stmt = stmt.where(Homework.grade_id == grade_id)
    stmt = stmt.order_by(Homework.submission_date.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())
