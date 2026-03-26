"""Insert people into the DB."""

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.db.models.student_representative import StudentRepresentative
from schoolai.skills.db.deduplicator import DedupeResult, MatchType

# /db usa etiquetas en español; el constraint de DB requiere valores en inglés
_ROLE_MAP: dict[str, str] = {
    "estudiante": "student",
    "docente": "teacher",
    "directivo": "executive",
    "administrativo": "admin",
    "representante": "parent",
    "representante_legal": "legal_representative",
    "autoridad": "authority",
}


@dataclass
class SaveResult:
    created: int
    skipped: int


async def save_people(
    results: list[DedupeResult],
    role: str,
    session: AsyncSession,
    grade_id: int | None = None,
    section: str | None = None,
) -> SaveResult:
    created = skipped = 0

    for r in results:
        match r.match_type:
            case MatchType.NEW:
                person = _build_person(r.parsed, role)
                session.add(person)
                await session.flush()  # get person.id

                if role == "estudiante" and grade_id and section:
                    session.add(
                        Student(
                            person_id=person.id,
                            grade_id=grade_id,
                            section=section,
                        ),
                    )
                created += 1

            case MatchType.EXACT_ID | MatchType.EXACT_NAME:
                # Person already exists — skip
                skipped += 1

            case MatchType.SIMILAR:
                skipped += 1

    await session.commit()
    return SaveResult(created=created, skipped=skipped)


async def link_representative(
    session: AsyncSession,
    student_id: int,
    person_id: int,
    relationship_type: str | None = None,
    make_primary: bool = False,
) -> None:
    """Vincula un representante a un estudiante en student_representatives.
    Si make_primary=True, quita el flag primario de los demás primero.
    """
    # Verificar si ya existe el vínculo
    existing = (
        await session.execute(
            select(StudentRepresentative).where(
                StudentRepresentative.student_id == student_id,
                StudentRepresentative.person_id == person_id,
            ),
        )
    ).scalar_one_or_none()

    if existing:
        existing.status = "active"
        if relationship_type:
            existing.relationship_type = relationship_type
        if make_primary:
            existing.is_primary_notify = True
    else:
        if make_primary:
            # Quitar primary a los demás antes de insertar el nuevo
            await session.execute(
                update(StudentRepresentative)
                .where(StudentRepresentative.student_id == student_id)
                .values(is_primary_notify=False),
            )
        # ¿Es el primero? → automáticamente primario
        any_existing = (
            await session.execute(
                select(StudentRepresentative.id)
                .where(StudentRepresentative.student_id == student_id)
                .limit(1),
            )
        ).first()
        session.add(
            StudentRepresentative(
                student_id=student_id,
                person_id=person_id,
                relationship_type=relationship_type,
                is_primary_notify=make_primary or any_existing is None,
                status="active",
            ),
        )
    await session.commit()


def _build_person(parsed: dict, role: str) -> Person:
    return Person(
        first_name=parsed.get("first_name", ""),
        middle_name=parsed.get("middle_name"),
        last_name=parsed.get("last_name", ""),
        second_last_name=parsed.get("second_last_name"),
        national_id=parsed.get("national_id"),
        role=_ROLE_MAP.get(role, role),
        status="active",
    )
