"""In-memory conversation state per user."""

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Literal


@dataclass
class PendingHomework:
    text: str
    grade_id: int
    grade_name: str
    delivery: date | None


# user_id -> pending homework waiting for subject
_pending: dict[int, PendingHomework] = {}


def set_pending(user_id: int, pending: PendingHomework) -> None:
    _pending[user_id] = pending
    _touch("pending", user_id)


def get_pending(user_id: int) -> PendingHomework | None:
    return _pending.get(user_id)


def clear_pending(user_id: int) -> None:
    _pending.pop(user_id, None)
    _expire("pending", user_id)


# ── DB Skill state ────────────────────────────────────────────────────────────

DbStep = Literal["await_list", "await_grade", "await_section", "await_confirm"]


@dataclass
class DbFlow:
    step: DbStep
    role: str
    parsed_names: list[dict] = field(default_factory=list)
    grade_id: int | None = None
    grade_name: str | None = None
    section: str | None = None
    dedup_results: list | None = None  # list[DedupeResult]


_db_flows: dict[int, DbFlow] = {}


def set_db_flow(user_id: int, flow: DbFlow) -> None:
    _db_flows[user_id] = flow
    _touch("db", user_id)


def get_db_flow(user_id: int) -> DbFlow | None:
    return _db_flows.get(user_id)


def clear_db_flow(user_id: int) -> None:
    _db_flows.pop(user_id, None)
    _expire("db", user_id)


# ── Attendance state ──────────────────────────────────────────────────────────

AttendanceStep = Literal["await_grade", "await_ambiguous"]


@dataclass
class PendingAttendance:
    step: AttendanceStep
    extracted: list[dict]            # [{"name": str, "status": "F"|"AT"|"J"}]
    attendance_date: date
    grade_id: int | None = None
    grade_name: str | None = None
    confirmed: list[dict] = field(default_factory=list)   # [{student_id, status}]
    ambiguous: list = field(default_factory=list)          # list[MatchResult] pending resolution


_attendance: dict[int, PendingAttendance] = {}


def set_attendance(user_id: int, state: PendingAttendance) -> None:
    _attendance[user_id] = state
    _touch("attendance", user_id)


def get_attendance(user_id: int) -> PendingAttendance | None:
    return _attendance.get(user_id)


def clear_attendance(user_id: int) -> None:
    _attendance.pop(user_id, None)
    _expire("attendance", user_id)


# ── Query state ───────────────────────────────────────────────────────────────

@dataclass
class QueryFlow:
    intent: object  # QueryIntent


_queries: dict[int, QueryFlow] = {}


def set_query(user_id: int, flow: QueryFlow) -> None:
    _queries[user_id] = flow
    _touch("query", user_id)


def get_query(user_id: int) -> QueryFlow | None:
    return _queries.get(user_id)


def clear_query(user_id: int) -> None:
    _queries.pop(user_id, None)
    _expire("query", user_id)


# ── TTL cleanup ───────────────────────────────────────────────────────────────

_timestamps: dict[str, dict[int, float]] = {
    "pending": {},
    "db": {},
    "attendance": {},
    "query": {},
}
_TTL = 1800  # 30 minutos


def _touch(store: str, user_id: int) -> None:
    _timestamps[store][user_id] = time.monotonic()


def _expire(store: str, user_id: int) -> None:
    _timestamps[store].pop(user_id, None)


def cleanup_stale() -> int:
    """Elimina estados expirados. Retorna cantidad eliminada."""
    now = time.monotonic()
    removed = 0
    for store, data_dict in [
        ("pending", _pending),
        ("db", _db_flows),
        ("attendance", _attendance),
        ("query", _queries),
    ]:
        expired = [uid for uid, ts in _timestamps[store].items() if now - ts > _TTL]
        for uid in expired:
            data_dict.pop(uid, None)
            _timestamps[store].pop(uid, None)
            removed += 1
    return removed
