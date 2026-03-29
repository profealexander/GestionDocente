from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.grade import Grade
from schoolai.db.models.homework import Homework
from schoolai.db.models.subject import Subject

_GRADE_ALIASES = {
    # Primero BT
    "1bt": "PRIMERO BT",
    "1 bt": "PRIMERO BT",
    "1bachi": "PRIMERO BT",
    "1bachillerato": "PRIMERO BT",
    "1ero bt": "PRIMERO BT",
    "1ro bt": "PRIMERO BT",
    "1er bt": "PRIMERO BT",
    "1° bt": "PRIMERO BT",
    "1o bt": "PRIMERO BT",
    "primer bt": "PRIMERO BT",
    "primero bt": "PRIMERO BT",
    "primero bachillerato": "PRIMERO BT",
    # Segundo BT
    "2bt": "SEGUNDO BT",
    "2 bt": "SEGUNDO BT",
    "2bachi": "SEGUNDO BT",
    "2bachillerato": "SEGUNDO BT",
    "2do bt": "SEGUNDO BT",
    "2dobt": "SEGUNDO BT",
    "2° bt": "SEGUNDO BT",
    "2da bt": "SEGUNDO BT",
    "segundo bt": "SEGUNDO BT",
    "segunda bt": "SEGUNDO BT",
    "segundo bachillerato": "SEGUNDO BT",
    "segunda bachillerato": "SEGUNDO BT",
    # Tercero BT
    "3bt": "TERCERO BT",
    "3 bt": "TERCERO BT",
    "3bachi": "TERCERO BT",
    "3bachillerato": "TERCERO BT",
    "3ero bt": "TERCERO BT",
    "3° bt": "TERCERO BT",
    "tercero bt": "TERCERO BT",
    "tercero bachillerato": "TERCERO BT",
    # EGB
    "2do egb": "SEGUNDO EGB",
    "2° egb": "SEGUNDO EGB",
    "segundo egb": "SEGUNDO EGB",
    "3ero egb": "TERCERO EGB",
    "3° egb": "TERCERO EGB",
    "tercero egb": "TERCERO EGB",
    "4to egb": "CUARTO EGB",
    "cuarto egb": "CUARTO EGB",
    "5to egb": "QUINTO EGB",
    "quinto egb": "QUINTO EGB",
    "6to egb": "SEXTO EGB",
    "sexto egb": "SEXTO EGB",
    "7mo egb": "SEPTIMO EGB",
    "séptimo egb": "SEPTIMO EGB",
    "septimo egb": "SEPTIMO EGB",
    "8vo egb": "OCTAVO EGB",
    "octavo egb": "OCTAVO EGB",
    "9no egb": "NOVENO EGB",
    "noveno egb": "NOVENO EGB",
    "10mo egb": "DECIMO EGB",
    "décimo egb": "DECIMO EGB",
    "decimo egb": "DECIMO EGB",
}


async def find_grade(session: AsyncSession, name: str) -> Grade | None:
    normalized = _GRADE_ALIASES.get(name.lower().strip())
    search = normalized or name.upper()
    result = await session.execute(
        select(Grade).where(Grade.name.ilike(f"%{search}%")).order_by(Grade.sort_order),
    )
    return result.scalars().first()


async def find_subject(session: AsyncSession, name: str) -> Subject | None:
    """Fuzzy search using pg_trgm similarity."""
    result = await session.execute(
        select(Subject)
        .where(func.similarity(func.lower(Subject.name), name.lower()) > 0.15)
        .order_by(func.similarity(func.lower(Subject.name), name.lower()).desc())
        .limit(1),
    )
    return result.scalars().first()


def _get_trimester_num(d: date) -> int:
    from schoolai.skills.query.detector import TRIMESTERS

    for num, start, end in TRIMESTERS:
        if start <= d <= end:
            return num
    return 0


async def save_homework(
    session: AsyncSession,
    homework: str,
    grade_id: int,
    subject_id: int | None = None,
    delivery_date: date | None = None,
    teacher_id: int | None = None,
) -> Homework:
    today = delivery_date or date.today()
    trimester = _get_trimester_num(today)

    # Deduplication: return existing if same description+grade+trimester+subject already exists
    dup_stmt = select(Homework).where(
        Homework.grade_id == grade_id,
        Homework.trimester_num == trimester,
        func.lower(Homework.homework) == homework.lower().strip(),
    )
    if subject_id:
        dup_stmt = dup_stmt.where(Homework.subject_id == subject_id)
    else:
        dup_stmt = dup_stmt.where(Homework.subject_id.is_(None))
    existing = (await session.execute(dup_stmt)).scalars().first()
    if existing:
        return existing

    # Calcular sequence_num con lock para evitar condición de carrera
    seq_stmt = (
        select(func.coalesce(func.max(Homework.sequence_num), 0))
        .where(
            Homework.grade_id == grade_id,
            Homework.trimester_num == trimester,
        )
        .with_for_update()
    )
    seq_num = (await session.scalar(seq_stmt)) + 1

    record = Homework(
        homework=homework,
        grade_id=grade_id,
        subject_id=subject_id,
        delivery_date=delivery_date,
        is_open=True,
        sequence_num=seq_num,
        trimester_num=trimester,
        teacher_id=teacher_id,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def list_open(session: AsyncSession, grade_id: int | None = None) -> list[Homework]:
    from datetime import date as _date

    current_trimester = _get_trimester_num(_date.today())
    stmt = select(Homework).where(
        Homework.is_open.is_(True),
        Homework.trimester_num == current_trimester,
    )
    if grade_id:
        stmt = stmt.where(Homework.grade_id == grade_id)
    stmt = stmt.order_by(Homework.submission_date.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_homework_by_ref(
    session: AsyncSession,
    sequence_num: int,
    grade_id: int,
    subject_id: int | None = None,
    trimester_num: int | None = None,
    any_trimester: bool = False,
) -> Homework | None:
    """Busca una tarea por número de secuencia y curso.

    Args:
        any_trimester: si True, ignora el filtro de trimestre. Usar en
                       operaciones de edición/borrado donde el docente referencia
                       la tarea por el número que vio en la lista (que puede
                       pertenecer a cualquier trimestre).
    """
    from datetime import date as _date

    stmt = select(Homework).where(
        Homework.grade_id == grade_id,
        Homework.sequence_num == sequence_num,
    )
    if not any_trimester:
        if trimester_num is None:
            trimester_num = _get_trimester_num(_date.today())
        stmt = stmt.where(Homework.trimester_num == trimester_num)
    if subject_id:
        stmt = stmt.where(Homework.subject_id == subject_id)
    result = await session.execute(stmt)
    return result.scalars().first()


async def save_non_completers(
    session: AsyncSession,
    homework_id: int,
    student_ids: list[int],
    status: str = "missing",
) -> int:
    from schoolai.db.models.homework_submission import HomeworkSubmission

    # Delete previous records for this homework (idempotent)
    existing = await session.execute(
        select(HomeworkSubmission).where(HomeworkSubmission.homework_id == homework_id),
    )
    for sub in existing.scalars().all():
        await session.delete(sub)

    for sid in student_ids:
        session.add(HomeworkSubmission(homework_id=homework_id, student_id=sid, status=status))

    await session.commit()
    return len(student_ids)


async def update_homework(session: AsyncSession, hw_id: int, **kwargs) -> Homework | None:
    """Actualiza campos de una tarea. kwargs: homework, delivery_date, subject_id, is_open."""
    hw = await session.get(Homework, hw_id)
    if not hw:
        return None
    for key, value in kwargs.items():
        setattr(hw, key, value)
    await session.commit()
    await session.refresh(hw)
    return hw


async def delete_homework(session: AsyncSession, hw_id: int) -> bool:
    """Elimina una tarea por ID. Las submissions se eliminan en cascada."""
    hw = await session.get(Homework, hw_id)
    if not hw:
        return False
    await session.delete(hw)
    await session.commit()
    return True


async def count_students_in_grade(session: AsyncSession, grade_id: int) -> int:
    from schoolai.db.models.student import Student

    result = await session.execute(
        select(func.count())
        .select_from(Student)
        .where(
            Student.grade_id == grade_id,
            Student.status == "active",
        ),
    )
    return result.scalar() or 0
