"""Insert people and their roles into the DB."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.person import Person, PersonRole
from schoolai.db.models.student import Student
from schoolai.skills.db.deduplicator import DedupeResult, MatchType


@dataclass
class SaveResult:
    created: int
    role_added: int
    skipped: int


async def save_people(
    results: list[DedupeResult],
    role: str,
    session: AsyncSession,
    grade_id: int | None = None,
    section: str | None = None,
) -> SaveResult:
    created = role_added = skipped = 0

    for r in results:
        match r.match_type:
            case MatchType.NEW:
                person = _build_person(r.parsed, role)
                session.add(person)
                await session.flush()  # get person.id

                session.add(PersonRole(person_id=person.id, role=role, is_primary=True))

                if role == "estudiante" and grade_id and section:
                    session.add(Student(
                        person_id=person.id,
                        grade_id=grade_id,
                        section=section,
                    ))
                created += 1

            case MatchType.EXACT_ID | MatchType.EXACT_NAME:
                # Add role if not already assigned
                if role not in r.existing_roles and r.existing_id:
                    session.add(PersonRole(
                        person_id=r.existing_id,
                        role=role,
                        is_primary=False,
                    ))
                    if role == "estudiante" and grade_id and section:
                        session.add(Student(
                            person_id=r.existing_id,
                            grade_id=grade_id,
                            section=section,
                        ))
                    role_added += 1
                else:
                    skipped += 1

            case MatchType.SIMILAR:
                # Similar matches are skipped — user should review manually
                skipped += 1

    await session.commit()
    return SaveResult(created=created, role_added=role_added, skipped=skipped)


def _build_person(parsed: dict, role: str) -> Person:
    return Person(
        first_name=parsed.get("first_name", ""),
        middle_name=parsed.get("middle_name"),
        last_name=parsed.get("last_name", ""),
        second_last_name=parsed.get("second_last_name"),
        national_id=parsed.get("national_id"),
        role=role,
        status="active",
    )
