"""Conversation state per user.

Two-layer persistence:
  L1 — in-memory dicts (fast, process-local)
  L2 — Redis (optional; survives restarts; loaded on cache miss)

If Redis is not configured or unavailable the system silently uses RAM only.
"""

import pickle
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from loguru import logger

# ── Redis backend (optional) ──────────────────────────────────────────────────

try:
    import redis as _redis_lib
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False

_redis_client: Any = None   # redis.Redis instance or None
_REDIS_TTL_SHORT = 3600     # 60 min — db/schedule/position/attendance/sel flows
_REDIS_TTL_JORNADA = 86400  # 24 h  — Modo Jornada session spans the school day


def init_redis(url: str) -> None:
    """Connect to Redis. Called once at bot startup. Safe to call with empty url."""
    global _redis_client
    if not _HAS_REDIS or not url:
        return
    try:
        client = _redis_lib.Redis.from_url(url, socket_timeout=2, decode_responses=False)
        client.ping()
        _redis_client = client
        logger.info(f"[state] Redis connected: {url}")
    except Exception as exc:
        logger.warning(f"[state] Redis unavailable — using in-memory only: {exc}")


def _rset(key: str, obj: object, ttl: int) -> None:
    if _redis_client is None:
        return
    try:
        _redis_client.setex(key, ttl, pickle.dumps(obj))
    except Exception as exc:
        logger.debug(f"[state] Redis set failed ({key}): {exc}")


def _rget(key: str) -> Any:
    if _redis_client is None:
        return None
    try:
        raw = _redis_client.get(key)
        return pickle.loads(raw) if raw else None  # nosec B301 — Redis es interno, solo el bot escribe
    except Exception as exc:
        logger.debug(f"[state] Redis get failed ({key}): {exc}")
        return None


def _rdel(key: str) -> None:
    if _redis_client is None:
        return
    try:
        _redis_client.delete(key)
    except Exception as exc:
        logger.debug(f"[state] Redis del failed ({key}): {exc}")


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


# ── Schedule Skill state ───────────────────────────────────────────────────────

ScheduleStep = Literal["await_teacher", "await_day", "await_periods", "await_confirm"]

# ── Position Skill state ───────────────────────────────────────────────────────

PositionStep = Literal[
    "await_teacher", "await_action", "await_type",
    "await_grade", "await_subnivel", "await_area", "await_cargo_val",
    "await_detail", "await_confirm_add",
]


@dataclass
class PositionFlow:
    step: PositionStep
    teacher_id: int | None = None
    teacher_name: str | None = None
    position_type: str | None = None
    grade_id: int | None = None
    grade_name: str | None = None
    subnivel: str | None = None
    area: str | None = None
    detail: str | None = None
    areas_list: list[str] = field(default_factory=list)


_position_flows: dict[int, PositionFlow] = {}


def set_position_flow(user_id: int, flow: PositionFlow) -> None:
    _position_flows[user_id] = flow
    _touch("position", user_id)
    _rset(f"pos:{user_id}", flow, _REDIS_TTL_SHORT)


def get_position_flow(user_id: int) -> PositionFlow | None:
    if user_id not in _position_flows:
        obj = _rget(f"pos:{user_id}")
        if obj is not None:
            _position_flows[user_id] = obj
            _touch("position", user_id)
    return _position_flows.get(user_id)


def clear_position_flow(user_id: int) -> None:
    _position_flows.pop(user_id, None)
    _expire("position", user_id)
    _rdel(f"pos:{user_id}")

DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


@dataclass
class ScheduleFlow:
    step: ScheduleStep
    teacher_id: int | None = None
    day_of_week: int | None = None          # 0-4
    parsed_periods: list[dict] = field(default_factory=list)   # resolved period dicts
    errors: list[str] = field(default_factory=list)


_schedule_flows: dict[int, ScheduleFlow] = {}


def set_schedule_flow(user_id: int, flow: ScheduleFlow) -> None:
    _schedule_flows[user_id] = flow
    _touch("schedule", user_id)
    _rset(f"sch:{user_id}", flow, _REDIS_TTL_SHORT)


def get_schedule_flow(user_id: int) -> ScheduleFlow | None:
    if user_id not in _schedule_flows:
        obj = _rget(f"sch:{user_id}")
        if obj is not None:
            _schedule_flows[user_id] = obj
            _touch("schedule", user_id)
    return _schedule_flows.get(user_id)


def clear_schedule_flow(user_id: int) -> None:
    _schedule_flows.pop(user_id, None)
    _expire("schedule", user_id)
    _rdel(f"sch:{user_id}")


def set_db_flow(user_id: int, flow: DbFlow) -> None:
    _db_flows[user_id] = flow
    _touch("db", user_id)
    _rset(f"db:{user_id}", flow, _REDIS_TTL_SHORT)


def get_db_flow(user_id: int) -> DbFlow | None:
    if user_id not in _db_flows:
        obj = _rget(f"db:{user_id}")
        if obj is not None:
            _db_flows[user_id] = obj
            _touch("db", user_id)
    return _db_flows.get(user_id)


def clear_db_flow(user_id: int) -> None:
    _db_flows.pop(user_id, None)
    _expire("db", user_id)
    _rdel(f"db:{user_id}")


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
    _rset(f"sel:{user_id}", pending, _REDIS_TTL_SHORT)


def get_selection(user_id: int) -> PendingSelection | None:
    if user_id not in _selections:
        obj = _rget(f"sel:{user_id}")
        if obj is not None:
            _selections[user_id] = obj
            _touch("sel", user_id)
    return _selections.get(user_id)


def clear_selection(user_id: int) -> None:
    _selections.pop(user_id, None)
    _expire("sel", user_id)
    _rdel(f"sel:{user_id}")


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
    _rset(f"att:{user_id}", state, _REDIS_TTL_SHORT)


def get_attendance(user_id: int) -> PendingAttendance | None:
    if user_id not in _attendance:
        obj = _rget(f"att:{user_id}")
        if obj is not None:
            _attendance[user_id] = obj
            _touch("attendance", user_id)
    return _attendance.get(user_id)


def clear_attendance(user_id: int) -> None:
    _attendance.pop(user_id, None)
    _expire("attendance", user_id)
    _rdel(f"att:{user_id}")


# ── Modo Jornada state ────────────────────────────────────────────────────────
#
# JornadaSession dura todo el día escolar — NO usa el TTL de 60 min.
# Se limpia al completar la jornada, pausar indefinidamente o a medianoche.
#
# status:
#   "waiting" — jornada iniciada, esperando confirmación de llegada al aula
#   "active"  — docente en clase, contexto grade+subject activo
#   "paused"  — docente pausó la jornada (receso, etc.)
#   "done"    — todos los períodos completados

JornadaStatus = Literal["waiting", "active", "paused", "done"]


@dataclass
class JornadaSession:
    teacher_id: int
    chat_id: int
    day_of_week: int
    periods: list[dict]           # [{period_num, start_time, end_time, grade_id, grade_name, subject_id, subject_name}]
    current_index: int = 0        # índice activo en periods (0-based)
    status: JornadaStatus = "waiting"
    # Contexto activo — se llena al confirmar llegada
    grade_id: int | None = None
    grade_name: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None

    @property
    def current_period(self) -> dict | None:
        if 0 <= self.current_index < len(self.periods):
            return self.periods[self.current_index]
        return None

    @property
    def has_next(self) -> bool:
        return self.current_index + 1 < len(self.periods)

    def clear_context(self) -> None:
        self.grade_id = self.grade_name = self.subject_id = self.subject_name = None


_jornada: dict[int, JornadaSession] = {}  # user_id → session


def set_jornada(user_id: int, session: JornadaSession) -> None:
    _jornada[user_id] = session
    _rset(f"jor:{user_id}", session, _REDIS_TTL_JORNADA)


def get_jornada(user_id: int) -> JornadaSession | None:
    if user_id not in _jornada:
        obj = _rget(f"jor:{user_id}")
        if obj is not None:
            _jornada[user_id] = obj
    return _jornada.get(user_id)


def clear_jornada(user_id: int) -> None:
    _jornada.pop(user_id, None)
    _rdel(f"jor:{user_id}")


def get_jornada_context(user_id: int) -> tuple[int | None, str | None, int | None, str | None]:
    """Returns (grade_id, grade_name, subject_id, subject_name) if jornada active, else Nones."""
    s = _jornada.get(user_id)
    if s and s.status == "active":
        return s.grade_id, s.grade_name, s.subject_id, s.subject_name
    return None, None, None, None


def clear_jornada_all_stale() -> int:
    """Limpia sesiones de jornada del día anterior."""
    today = date.today().weekday()  # 0-4
    stale = [uid for uid, s in _jornada.items() if s.day_of_week != today]
    for uid in stale:
        _jornada.pop(uid, None)
    return len(stale)


# ── TTL cleanup ───────────────────────────────────────────────────────────────

_timestamps: dict[str, dict[int, float]] = {
    "db": {},
    "attendance": {},
    "sel": {},
    "schedule": {},
    "position": {},
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
        ("schedule", _schedule_flows),
        ("position", _position_flows),
    ]:
        expired = [uid for uid, ts in _timestamps[store].items() if now - ts > _TTL]
        for uid in expired:
            data_dict.pop(uid, None)
            _timestamps[store].pop(uid, None)
            removed += 1
    return removed
