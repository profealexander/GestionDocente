"""Check parsed names against the DB and classify each one."""

from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.person import Person
from schoolai.skills.db.parser import format_name
from schoolai.skills.utils.text import normalize


class MatchType(Enum):
    NEW = "new"
    EXACT_ID = "exact_id"  # matched by cédula
    EXACT_NAME = "exact_name"  # normalized first+last match
    SIMILAR = "similar"  # first name matches, last name similar


@dataclass
class DedupeResult:
    parsed: dict
    match_type: MatchType
    existing_id: int | None = None
    existing_name: str | None = None
    existing_roles: list[str] = field(default_factory=list)


async def deduplicate(parsed_list: list[dict], session: AsyncSession) -> list[DedupeResult]:
    return [await _check_one(parsed, session) for parsed in parsed_list]


async def _check_one(parsed: dict, session: AsyncSession) -> DedupeResult:
    # 1 — match by cédula (most reliable)
    if parsed.get("national_id"):
        stmt = select(Person).where(Person.national_id == parsed["national_id"])
        person = (await session.execute(stmt)).scalars().first()
        if person:
            return DedupeResult(
                parsed=parsed,
                match_type=MatchType.EXACT_ID,
                existing_id=person.id,
                existing_name=person.full_name(),
                existing_roles=_role_names(person),
            )

    first = normalize(parsed.get("first_name", ""))
    last = normalize(parsed.get("last_name", ""))

    if not first:
        return DedupeResult(parsed=parsed, match_type=MatchType.NEW)

    # 2 — exact name match (normalized)
    if last:
        stmt = select(Person).where(
            func.upper(func.unaccent(Person.first_name)) == first,
            func.upper(func.unaccent(Person.last_name)) == last,
        )
        person = (await session.execute(stmt)).scalars().first()
        if person:
            return DedupeResult(
                parsed=parsed,
                match_type=MatchType.EXACT_NAME,
                existing_id=person.id,
                existing_name=person.full_name(),
                existing_roles=_role_names(person),
            )

    # 3 — similar: first name exact, last name contains or is contained
    if last:
        stmt = select(Person).where(
            func.upper(func.unaccent(Person.first_name)) == first,
        )
        candidates = (await session.execute(stmt)).scalars().all()
        for p in candidates:
            p_last = normalize(p.last_name or "")
            if last in p_last or p_last in last:
                return DedupeResult(
                    parsed=parsed,
                    match_type=MatchType.SIMILAR,
                    existing_id=p.id,
                    existing_name=p.full_name(),
                    existing_roles=_role_names(p),
                )

    return DedupeResult(parsed=parsed, match_type=MatchType.NEW)


def _role_names(person: Person) -> list[str]:
    return [r.role for r in (person.roles or [])]


def build_preview_lines(results: list[DedupeResult], new_role: str) -> list[str]:
    """Format results for display in Telegram."""
    lines = []
    for r in results:
        name = format_name(r.parsed)
        match r.match_type:
            case MatchType.NEW:
                lines.append(f"✅ {name}")
            case MatchType.EXACT_ID:
                roles = ", ".join(r.existing_roles) or "sin roles"
                lines.append(f"⚠️ {name} → existe ({roles}) ¿agregar {new_role}?")
            case MatchType.EXACT_NAME:
                roles = ", ".join(r.existing_roles) or "sin roles"
                lines.append(f"⚠️ {name} → nombre exacto ({roles}) ¿agregar {new_role}?")
            case MatchType.SIMILAR:
                lines.append(f"❓ {name} → similar a *{r.existing_name}* ¿es el mismo?")
    return lines
