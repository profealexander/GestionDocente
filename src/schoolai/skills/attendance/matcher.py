"""Match extracted name strings to actual students in the DB."""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.skills.utils.text import normalize as _norm

SIMILARITY_THRESHOLD = 0.80  # mínimo para considerar nombre similar


class _StudentEntry(NamedTuple):
    student: object
    display: str
    short: str
    norm_short: str  # pre-normalizado para fuzzy matching — evita re-normalizar en cada check


@dataclass
class MatchResult:
    raw_name: str
    status: str  # 'F' | 'AT' | 'J'
    matched_id: int | None = None  # student.id if resolved
    matched_name: str | None = None
    candidates: list[dict] = field(default_factory=list)  # [{id, name}] if ambiguous

    @property
    def resolved(self) -> bool:
        return self.matched_id is not None

    @property
    def ambiguous(self) -> bool:
        return not self.resolved and len(self.candidates) > 1

    @property
    def not_found(self) -> bool:
        return not self.resolved and len(self.candidates) == 0


async def match_names(
    extracted: list[dict],
    grade_id: int,
    session: AsyncSession,
) -> list[MatchResult]:
    """Match each extracted name against students of the given grade."""
    # Load all students for this grade with their person info
    stmt = (
        select(Student)
        .where(Student.grade_id == grade_id, Student.status == "active")
        .order_by(Student.id)
    )
    students = (await session.execute(stmt)).unique().scalars().all()

    # Build lookup structures
    by_id: dict[int, _StudentEntry] = {}  # student.id → _StudentEntry
    by_first: dict[str, list[int]] = {}  # norm first_name → [student_ids]
    by_last: dict[str, list[int]] = {}  # norm last_name → [student_ids]
    by_full: dict[str, int] = {}  # norm name variant → student_id

    for s in students:
        if not s.person:
            continue
        p: Person = s.person
        short = f"{p.first_name} {p.last_name}".strip()
        if p.second_last_name:
            full_long = f"{p.first_name} {p.last_name} {p.second_last_name}"
        else:
            full_long = short

        display = p.full_name()
        by_id[s.id] = _StudentEntry(
            student=s, display=display, short=short, norm_short=_norm(short),
        )
        by_full[_norm(short)] = s.id
        by_full[_norm(full_long)] = s.id
        # Variantes con apellido primero: "Recalde David", "Recalde Montenegro David Leodan"
        by_full[_norm(f"{p.last_name} {p.first_name}")] = s.id
        if p.middle_name:
            by_full[_norm(f"{p.last_name} {p.first_name} {p.middle_name}")] = s.id
        if p.second_last_name:
            by_full[_norm(f"{p.last_name} {p.second_last_name} {p.first_name}")] = s.id

        by_first.setdefault(_norm(p.first_name), []).append(s.id)
        if p.middle_name:
            by_first.setdefault(_norm(p.middle_name), []).append(s.id)

        by_last.setdefault(_norm(p.last_name), []).append(s.id)
        if p.second_last_name:
            by_last.setdefault(_norm(p.second_last_name), []).append(s.id)

    results: list[MatchResult] = []
    for item in extracted:
        result = _match_one(item["name"], item["status"], by_id, by_first, by_last, by_full)
        results.append(result)

    return results


def _match_one(
    raw: str,
    status: str,
    by_id: dict,
    by_first: dict,
    by_last: dict,
    by_full: dict,
) -> MatchResult:
    parts = raw.strip().split()

    if not parts:
        return MatchResult(raw_name=raw, status=status)

    # Try full name match first (2+ words)
    if len(parts) >= 2:
        norm_full = _norm(raw)
        if norm_full in by_full:
            sid = by_full[norm_full]
            display = by_id[sid].display
            return MatchResult(raw_name=raw, status=status, matched_id=sid, matched_name=display)

        # Try first word as first_name + rest as last_name combinations
        for split in range(1, len(parts)):
            first = _norm(" ".join(parts[:split]))
            last = _norm(" ".join(parts[split:]))
            candidate_key = f"{first} {last}"
            if candidate_key in by_full:
                sid = by_full[candidate_key]
                display = by_id[sid].display
                return MatchResult(
                    raw_name=raw, status=status, matched_id=sid, matched_name=display,
                )

    # Try first name only (exact)
    norm_first = _norm(parts[0])
    ids = by_first.get(norm_first, [])

    if len(ids) == 1:
        sid = ids[0]
        return MatchResult(
            raw_name=raw, status=status, matched_id=sid, matched_name=by_id[sid].display,
        )

    if len(ids) > 1:
        candidates = [
            {"id": sid, "name": by_id[sid].display, "short": by_id[sid].short} for sid in ids
        ]
        return MatchResult(raw_name=raw, status=status, candidates=candidates)

    # Try last name only (exact)
    ids = by_last.get(norm_first, [])

    if len(ids) == 1:
        sid = ids[0]
        return MatchResult(
            raw_name=raw, status=status, matched_id=sid, matched_name=by_id[sid].display,
        )

    if len(ids) > 1:
        candidates = [
            {"id": sid, "name": by_id[sid].display, "short": by_id[sid].short} for sid in ids
        ]
        return MatchResult(raw_name=raw, status=status, candidates=candidates)

    # Fuzzy match — compare against pre-normalized short name (first + last)
    # Uses real_quick_ratio → quick_ratio → ratio cascade: 3-4x faster than ratio() alone
    norm_raw = _norm(raw)
    fuzzy_hits: list[tuple[float, int]] = []
    for sid, entry in by_id.items():
        sm = SequenceMatcher(None, norm_raw, entry.norm_short)
        if (
            sm.real_quick_ratio() >= SIMILARITY_THRESHOLD
            and sm.quick_ratio() >= SIMILARITY_THRESHOLD
        ):
            score = sm.ratio()
            if score >= SIMILARITY_THRESHOLD:
                fuzzy_hits.append((score, sid))

    fuzzy_hits.sort(reverse=True)

    if len(fuzzy_hits) == 1:
        sid = fuzzy_hits[0][1]
        return MatchResult(
            raw_name=raw, status=status, matched_id=sid, matched_name=by_id[sid].display,
        )

    if len(fuzzy_hits) > 1:
        candidates = [
            {"id": sid, "name": by_id[sid].display, "short": by_id[sid].short}
            for _, sid in fuzzy_hits
        ]
        return MatchResult(raw_name=raw, status=status, candidates=candidates)

    return MatchResult(raw_name=raw, status=status)
