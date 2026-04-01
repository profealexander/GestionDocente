from datetime import date

from sqlalchemy import distinct, func, select
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
    # Primero BT — variantes de voz (STT): "be te", "vt", "v t", "vete"
    "primero be te": "PRIMERO BT",
    "primero bete": "PRIMERO BT",
    "primero vt": "PRIMERO BT",
    "primero v t": "PRIMERO BT",
    "primero vete": "PRIMERO BT",
    "1ero be te": "PRIMERO BT",
    "1ero vt": "PRIMERO BT",
    "1ero vete": "PRIMERO BT",
    "primer be te": "PRIMERO BT",
    "primer vt": "PRIMERO BT",
    "primer vete": "PRIMERO BT",
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
    # Segundo BT — variantes de voz
    "segundo be te": "SEGUNDO BT",
    "segundo bete": "SEGUNDO BT",
    "segundo vt": "SEGUNDO BT",
    "segundo v t": "SEGUNDO BT",
    "segundo vete": "SEGUNDO BT",
    "2do be te": "SEGUNDO BT",
    "2do vt": "SEGUNDO BT",
    "2do vete": "SEGUNDO BT",
    # Tercero BT
    "3bt": "TERCERO BT",
    "3 bt": "TERCERO BT",
    "3bachi": "TERCERO BT",
    "3bachillerato": "TERCERO BT",
    "3ero bt": "TERCERO BT",
    "3° bt": "TERCERO BT",
    "tercero bt": "TERCERO BT",
    "tercero bachillerato": "TERCERO BT",
    # Tercero BT — variantes de voz
    "tercero be te": "TERCERO BT",
    "tercero bete": "TERCERO BT",
    "tercero vt": "TERCERO BT",
    "tercero v t": "TERCERO BT",
    "tercero vete": "TERCERO BT",
    "3ero be te": "TERCERO BT",
    "3ero vt": "TERCERO BT",
    "3ero vete": "TERCERO BT",
    # EGB con sufijo
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
    # EGB sin sufijo — cuarto–décimo (4to-10mo básica superior)
    "cuarto": "CUARTO EGB",
    "4to": "CUARTO EGB",
    "4": "CUARTO EGB",
    "quinto": "QUINTO EGB",
    "5to": "QUINTO EGB",
    "5": "QUINTO EGB",
    "sexto": "SEXTO EGB",
    "6to": "SEXTO EGB",
    "6": "SEXTO EGB",
    "séptimo": "SEPTIMO EGB",
    "septimo": "SEPTIMO EGB",
    "7mo": "SEPTIMO EGB",
    "7": "SEPTIMO EGB",
    "octavo": "OCTAVO EGB",
    "8vo": "OCTAVO EGB",
    "8": "OCTAVO EGB",
    "noveno": "NOVENO EGB",
    "9no": "NOVENO EGB",
    "9": "NOVENO EGB",
    "décimo": "DECIMO EGB",
    "decimo": "DECIMO EGB",
    "10mo": "DECIMO EGB",
    "10": "DECIMO EGB",
}


def _normalize_grade_key(s: str) -> str:
    """Minúsculas + sin tildes + sin espacios extra."""
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


async def find_grade(session: AsyncSession, name: str) -> Grade | None:
    key = _normalize_grade_key(name)
    normalized = _GRADE_ALIASES.get(key)
    search = normalized or name.upper()
    result = await session.execute(
        select(Grade).where(Grade.name.ilike(f"%{search}%")).order_by(Grade.sort_order),
    )
    return result.scalars().first()


async def find_subject(session: AsyncSession, name: str) -> Subject | None:
    """Fuzzy search using pg_trgm similarity. Checks aliases first."""
    from schoolai.skills.homework.detector import SUBJECT_ALIASES, _normalize_alias

    # Alias exacto (cubre abreviaturas cortas como "gc", "pcp")
    resolved = SUBJECT_ALIASES.get(_normalize_alias(name), name)

    result = await session.execute(
        select(Subject)
        .where(func.similarity(func.lower(Subject.name), resolved.lower()) > 0.15)
        .order_by(func.similarity(func.lower(Subject.name), resolved.lower()).desc())
        .limit(1),
    )
    return result.scalars().first()


async def get_teacher_subject_ids(
    session: AsyncSession,
    teacher_id: int,
    grade_id: int | None = None,
) -> list[int]:
    """Returns distinct subject IDs the teacher is scheduled to teach.

    If grade_id is given, restricts to that grade only.
    Returns [] if teacher has no active schedule (caller should treat as "no restriction").
    """
    from schoolai.db.models.teacher import Schedule

    stmt = select(distinct(Schedule.subject_id)).where(
        Schedule.teacher_id == teacher_id,
        Schedule.is_active.is_(True),
    )
    if grade_id is not None:
        stmt = stmt.where(Schedule.grade_id == grade_id)
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


async def get_teacher_subjects(
    session: AsyncSession,
    teacher_id: int,
    grade_id: int,
) -> list["Subject"]:  # noqa: F821
    """Returns Subject objects the teacher teaches in a specific grade."""
    from schoolai.db.models.teacher import Schedule

    rows = (
        await session.execute(
            select(Schedule.subject_id)
            .where(
                Schedule.teacher_id == teacher_id,
                Schedule.grade_id == grade_id,
                Schedule.is_active.is_(True),
            )
            .distinct()
        )
    ).all()
    subject_ids = [r[0] for r in rows]
    if not subject_ids:
        return []
    subjects = (
        await session.execute(select(Subject).where(Subject.id.in_(subject_ids)))
    ).scalars().all()
    return list(subjects)


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

    # Calcular sequence_num: MAX global por curso + trimestre (para búsqueda interna)
    seq_stmt = select(func.coalesce(func.max(Homework.sequence_num), 0)).where(
        Homework.grade_id == grade_id,
        Homework.trimester_num == trimester,
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


async def list_open(
    session: AsyncSession,
    grade_id: int | None = None,
    teacher_id: int | None = None,
    subject_id: int | None = None,
) -> list[Homework]:
    from datetime import date as _date

    current_trimester = _get_trimester_num(_date.today())
    stmt = select(Homework).where(
        Homework.is_open.is_(True),
        Homework.trimester_num == current_trimester,
    )
    if grade_id:
        stmt = stmt.where(Homework.grade_id == grade_id)
    if teacher_id:
        stmt = stmt.where(Homework.teacher_id == teacher_id)
    if subject_id:
        stmt = stmt.where(Homework.subject_id == subject_id)
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
    # Filtrar por materia si se provee — la numeración es por materia
    if subject_id is not None:
        stmt = stmt.where(Homework.subject_id == subject_id)
    result = await session.execute(stmt)
    return result.scalars().first()


async def save_non_completers(
    session: AsyncSession,
    homework_id: int,
    student_ids: list[int],
    status: str = "missing",
    *,
    commit: bool = True,
) -> int:
    from sqlalchemy import delete as _delete

    from schoolai.db.models.homework_submission import HomeworkSubmission

    # Bulk delete previous records for this homework (idempotent)
    await session.execute(
        _delete(HomeworkSubmission).where(HomeworkSubmission.homework_id == homework_id),
    )

    for sid in student_ids:
        session.add(HomeworkSubmission(homework_id=homework_id, student_id=sid, status=status))

    if commit:
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
