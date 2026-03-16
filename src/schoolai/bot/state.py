"""In-memory conversation state per user."""

import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal


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


# ── Unified selection state ───────────────────────────────────────────────────
#
# Covers three disambiguation flows:
#   "att_student"  — pick which student was absent (attendance)
#   "hw_task"      — pick which homework task (report)
#   "hw_student"   — pick which student for homework report; may chain to hw_task
#
# options: [{label: str, value: str}]   (value is the DB id as string)
# payload: action-specific dict (see action_handler.py for details)

SelectionAction = Literal["att_student", "hw_task", "hw_student"]


@dataclass
class PendingSelection:
    chat_id: int
    prompt: str
    options: list[dict]          # [{label: str, value: str}]
    action: SelectionAction
    payload: dict[str, Any]      # depends on action


_selections: dict[int, PendingSelection] = {}


def set_selection(user_id: int, pending: PendingSelection) -> None:
    _selections[user_id] = pending
    _touch("sel", user_id)


def get_selection(user_id: int) -> PendingSelection | None:
    return _selections.get(user_id)


def clear_selection(user_id: int) -> None:
    _selections.pop(user_id, None)
    _expire("sel", user_id)


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


# ── TTL cleanup ───────────────────────────────────────────────────────────────

_timestamps: dict[str, dict[int, float]] = {
    "db": {},
    "attendance": {},
    "sel": {},
}
_TTL = 3600  # 60 minutos


def _touch(store: str, user_id: int) -> None:
    _timestamps[store][user_id] = time.monotonic()


def _expire(store: str, user_id: int) -> None:
    _timestamps[store].pop(user_id, None)


def cleanup_stale() -> int:
    """Elimina estados expirados. Retorna cantidad eliminada."""
    now = time.monotonic()
    removed = 0
    for store, data_dict in [
        ("db", _db_flows),
        ("attendance", _attendance),
        ("sel", _selections),
    ]:
        expired = [uid for uid, ts in _timestamps[store].items() if now - ts > _TTL]
        for uid in expired:
            data_dict.pop(uid, None)
            _timestamps[store].pop(uid, None)
            removed += 1
    return removed
