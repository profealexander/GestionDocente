"""In-memory conversation state per user."""

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


def get_pending(user_id: int) -> PendingHomework | None:
    return _pending.get(user_id)


def clear_pending(user_id: int) -> None:
    _pending.pop(user_id, None)


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


def get_db_flow(user_id: int) -> DbFlow | None:
    return _db_flows.get(user_id)


def clear_db_flow(user_id: int) -> None:
    _db_flows.pop(user_id, None)


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


def get_attendance(user_id: int) -> PendingAttendance | None:
    return _attendance.get(user_id)


def clear_attendance(user_id: int) -> None:
    _attendance.pop(user_id, None)


# ── Query state ───────────────────────────────────────────────────────────────

@dataclass
class QueryFlow:
    intent: object  # QueryIntent


_queries: dict[int, QueryFlow] = {}


def set_query(user_id: int, flow: QueryFlow) -> None:
    _queries[user_id] = flow


def get_query(user_id: int) -> QueryFlow | None:
    return _queries.get(user_id)


def clear_query(user_id: int) -> None:
    _queries.pop(user_id, None)
