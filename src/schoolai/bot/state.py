"""Conversation state per user.

Two-layer persistence:
  L1 — in-memory dicts (fast, process-local)
  L2 — Redis (optional; survives restarts; loaded on cache miss)

If Redis is not configured or unavailable the system silently uses RAM only.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from loguru import logger

from schoolai.bot.state_store import (
    StateStore,
    cleanup_all_stale,  # re-export
    clear_all_user_state,  # re-export
)
from schoolai.bot.state_store import (
    init_redis as _ss_init_redis,
)

# Re-export for callers
__all__ = [
    "clear_all_user_state",
    "cleanup_all_stale",
]

# ── Redis TTL constants (kept for backward compat) ────────────────────────────

_REDIS_TTL_SHORT = 3600   # 60 min
_REDIS_TTL_JORNADA = 86400  # 24 h


def init_redis(url: str) -> None:
    """Connect to Redis. Called once at bot startup. Safe to call with empty url."""
    if not url:
        return
    try:
        import redis as _redis_lib
        client = _redis_lib.Redis.from_url(url, socket_timeout=2, decode_responses=False)
        client.ping()
        _ss_init_redis(client)
        logger.info(f"[state] Redis connected: {url}")
    except ImportError:
        logger.warning("[state] redis package not installed — using in-memory only")
    except Exception as exc:
        logger.warning(f"[state] Redis unavailable — using in-memory only: {exc}")


# ── DB Skill state ────────────────────────────────────────────────────────────

DbStep = Literal[
    "await_list", "await_grade", "await_section", "await_confirm", "await_link_student",
]


@dataclass
class DbFlow:
    step: DbStep
    role: str
    parsed_names: list[dict] = field(default_factory=list)
    grade_id: int | None = None
    grade_name: str | None = None
    section: str | None = None
    dedup_results: list | None = None  # list[DedupeResult]
    saved_person_ids: list[int] = field(default_factory=list)  # IDs creados tras confirmar


_db_store: StateStore[DbFlow] = StateStore("db", use_redis=True, ttl=_REDIS_TTL_SHORT)


def set_db_flow(user_id: int, flow: DbFlow) -> None:
    _db_store.set(user_id, flow)


def get_db_flow(user_id: int) -> DbFlow | None:
    return _db_store.get(user_id)


def clear_db_flow(user_id: int) -> None:
    _db_store.clear(user_id)


# ── Schedule Skill state ───────────────────────────────────────────────────────

ScheduleStep = Literal["await_teacher", "await_day", "await_periods", "await_confirm"]

# ── Position Skill state ───────────────────────────────────────────────────────

PositionStep = Literal[
    "await_teacher",
    "await_action",
    "await_type",
    "await_grade",
    "await_subnivel",
    "await_area",
    "await_cargo_val",
    "await_detail",
    "await_confirm_add",
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


_position_store: StateStore[PositionFlow] = StateStore(
    "position", use_redis=True, ttl=_REDIS_TTL_SHORT,
)


def set_position_flow(user_id: int, flow: PositionFlow) -> None:
    _position_store.set(user_id, flow)


def get_position_flow(user_id: int) -> PositionFlow | None:
    return _position_store.get(user_id)


def clear_position_flow(user_id: int) -> None:
    _position_store.clear(user_id)


DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]


@dataclass
class ScheduleFlow:
    step: ScheduleStep
    teacher_id: int | None = None
    day_of_week: int | None = None  # 0-4
    parsed_periods: list[dict] = field(default_factory=list)  # resolved period dicts
    errors: list[str] = field(default_factory=list)


_schedule_store: StateStore[ScheduleFlow] = StateStore(
    "schedule", use_redis=True, ttl=_REDIS_TTL_SHORT,
)


def set_schedule_flow(user_id: int, flow: ScheduleFlow) -> None:
    _schedule_store.set(user_id, flow)


def get_schedule_flow(user_id: int) -> ScheduleFlow | None:
    return _schedule_store.get(user_id)


def clear_schedule_flow(user_id: int) -> None:
    _schedule_store.clear(user_id)


# ── Unified selection state ───────────────────────────────────────────────────

SelectionAction = Literal["att_student", "hw_task", "hw_student"]


@dataclass
class PendingSelection:
    chat_id: int
    prompt: str
    options: list[dict]  # [{label: str, value: str}]
    action: SelectionAction
    payload: dict[str, Any]  # depends on action


_selection_store: StateStore[PendingSelection] = StateStore(
    "sel", use_redis=True, ttl=_REDIS_TTL_SHORT,
)


def set_selection(user_id: int, pending: PendingSelection) -> None:
    _selection_store.set(user_id, pending)


def get_selection(user_id: int) -> PendingSelection | None:
    return _selection_store.get(user_id)


def clear_selection(user_id: int) -> None:
    _selection_store.clear(user_id)


# ── Attendance state ──────────────────────────────────────────────────────────

AttendanceStep = Literal["await_grade", "await_ambiguous"]


@dataclass
class PendingAttendance:
    step: AttendanceStep
    extracted: list[dict]  # [{"name": str, "status": "F"|"AT"|"J"}]
    attendance_date: date
    grade_id: int | None = None
    grade_name: str | None = None
    confirmed: list[dict] = field(default_factory=list)  # [{student_id, status}]
    ambiguous: list = field(default_factory=list)  # list[MatchResult] pending resolution


_attendance_store: StateStore[PendingAttendance] = StateStore(
    "attendance", use_redis=True, ttl=_REDIS_TTL_SHORT,
)


def set_attendance(user_id: int, state: PendingAttendance) -> None:
    _attendance_store.set(user_id, state)


def get_attendance(user_id: int) -> PendingAttendance | None:
    return _attendance_store.get(user_id)


def clear_attendance(user_id: int) -> None:
    _attendance_store.clear(user_id)


# ── Modo Jornada state ────────────────────────────────────────────────────────

JornadaStatus = Literal["waiting", "active", "paused", "done"]


@dataclass
class JornadaSession:
    teacher_id: int
    chat_id: int
    day_of_week: int
    periods: list[
        dict
    ]  # [{period_num, start_time, end_time, grade_id, grade_name, subject_id, subject_name}]
    current_index: int = 0  # índice activo en periods (0-based)
    status: JornadaStatus = "waiting"
    # Contexto activo — se llena al confirmar llegada
    grade_id: int | None = None
    grade_name: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    # Ausencias del docente registradas durante la jornada
    # [{period_num, grade_name, subject_name, reason, reason_label}]
    absences: list[dict] = field(default_factory=list)

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


_jornada_store: StateStore[JornadaSession] = StateStore(
    "jornada", use_redis=True, ttl=_REDIS_TTL_JORNADA,
)


def set_jornada(user_id: int, session: JornadaSession) -> None:
    _jornada_store.set(user_id, session)


def get_jornada(user_id: int) -> JornadaSession | None:
    return _jornada_store.get(user_id)


def clear_jornada(user_id: int) -> None:
    _jornada_store.clear(user_id)


def get_jornada_context(user_id: int) -> tuple[int | None, str | None, int | None, str | None]:
    """Returns (grade_id, grade_name, subject_id, subject_name) if jornada active or waiting."""
    s = _jornada_store.get(user_id)
    if not s:
        return None, None, None, None
    if s.status == "active":
        return s.grade_id, s.grade_name, s.subject_id, s.subject_name
    # "waiting": tarjeta de período visible → usar current_period como contexto
    if s.status == "waiting" and s.current_period:
        p = s.current_period
        return p.get("grade_id"), p.get("grade_name"), p.get("subject_id"), p.get("subject_name")
    return None, None, None, None


def iter_all_jornada() -> list[tuple[int, "JornadaSession"]]:
    """Retorna todas las sesiones de jornada activas (memoria + Redis)."""
    return _jornada_store.scan_all()


def clear_jornada_all_stale() -> int:
    """Limpia sesiones de jornada del día anterior."""
    today = date.today().weekday()  # 0-4
    stale = [uid for uid, s in _jornada_store._data.items() if s.day_of_week != today]
    for uid in stale:
        _jornada_store._data.pop(uid, None)
        _jornada_store._timestamps.pop(uid, None)
    return len(stale)


# ── Pending course context ────────────────────────────────────────────────────


@dataclass
class PendingCourseContext:
    course_abbrev: str
    grade_id: int
    grade_name: str
    pending_intent: str  # "homework" | "attendance" | "homework_report"


_course_store: StateStore[PendingCourseContext] = StateStore(
    "course", use_redis=True, ttl=_REDIS_TTL_SHORT,
)


def set_course_context(user_id: int, ctx: PendingCourseContext) -> None:
    _course_store.set(user_id, ctx)


def get_course_context(user_id: int) -> PendingCourseContext | None:
    return _course_store.get(user_id)


def clear_course_context(user_id: int) -> None:
    _course_store.clear(user_id)


# ── WhatsApp notification state ───────────────────────────────────────────────

WhatsAppSetupStep = Literal["await_rep_name", "await_phone"]


@dataclass
class PendingWhatsAppNotification:
    chat_id: int
    hw_id: int
    hw_seq: int
    subject: str
    grade_name: str
    delivery_date: str  # "dd/mm/YYYY" or ""
    student_ids: list[int]
    student_names: list[str]


@dataclass
class PendingWhatsAppSetup:
    step: WhatsAppSetupStep
    guardian_id: int  # 0 si aún no se ha creado (step await_rep_name)
    guardian_name: str
    student_name: str
    student_id: int = 0  # para vincular al crear representante nuevo
    phone: str = ""


_wa_notification_store: StateStore[PendingWhatsAppNotification] = StateStore(
    "wan", use_redis=True, ttl=_REDIS_TTL_SHORT,
)
_wa_setup_store: StateStore[PendingWhatsAppSetup] = StateStore(
    "was", use_redis=True, ttl=_REDIS_TTL_SHORT,
)


def set_wa_notification(user_id: int, n: PendingWhatsAppNotification) -> None:
    _wa_notification_store.set(user_id, n)


def get_wa_notification(user_id: int) -> PendingWhatsAppNotification | None:
    return _wa_notification_store.get(user_id)


def clear_wa_notification(user_id: int) -> None:
    _wa_notification_store.clear(user_id)


def set_wa_setup(user_id: int, s: PendingWhatsAppSetup) -> None:
    _wa_setup_store.set(user_id, s)


def get_wa_setup(user_id: int) -> PendingWhatsAppSetup | None:
    return _wa_setup_store.get(user_id)


def clear_wa_setup(user_id: int) -> None:
    _wa_setup_store.clear(user_id)


# ── Pending cuota participante ────────────────────────────────────────────────


@dataclass
class PendingCuotaParticipante:
    actividad_id: int
    actividad_nombre: str


_cuota_participante_store: StateStore[PendingCuotaParticipante] = StateStore(
    "cuota_part", ttl=_REDIS_TTL_SHORT,
)


def set_cuota_participante(user_id: int, state: PendingCuotaParticipante) -> None:
    _cuota_participante_store.set(user_id, state)


def get_cuota_participante(user_id: int) -> PendingCuotaParticipante | None:
    return _cuota_participante_store.get(user_id)


def clear_cuota_participante(user_id: int) -> None:
    _cuota_participante_store.clear(user_id)


# ── Pending cuota nombre ──────────────────────────────────────────────────────


@dataclass
class PendingCuotaNombre:
    monto: float | None  # monto ya conocido, puede ser None si tampoco lo tiene
    course: str | None


_cuota_nombre_store: StateStore[PendingCuotaNombre] = StateStore(
    "cuota_nombre", ttl=_REDIS_TTL_SHORT,
)


def set_cuota_nombre(user_id: int, state: PendingCuotaNombre) -> None:
    _cuota_nombre_store.set(user_id, state)


def get_cuota_nombre(user_id: int) -> PendingCuotaNombre | None:
    return _cuota_nombre_store.get(user_id)


def clear_cuota_nombre(user_id: int) -> None:
    _cuota_nombre_store.clear(user_id)


# ── Pending homework edit field ───────────────────────────────────────────────


@dataclass
class PendingHwEditField:
    hw_id: int
    hw_seq: int
    grade_name: str
    field: str  # "descripcion" | "fecha" | "materia"


_hw_edit_store: StateStore[PendingHwEditField] = StateStore(
    "hw_edit", ttl=_REDIS_TTL_SHORT,
)


def set_hw_edit_field(user_id: int, state: PendingHwEditField) -> None:
    _hw_edit_store.set(user_id, state)


def get_hw_edit_field(user_id: int) -> PendingHwEditField | None:
    return _hw_edit_store.get(user_id)


def clear_hw_edit_field(user_id: int) -> None:
    _hw_edit_store.clear(user_id)


# ── Pending cuota edit field ──────────────────────────────────────────────────


@dataclass
class PendingCuotaEditField:
    actividad_id: int
    actividad_nombre: str
    field: str  # "nombre" | "monto" | "descripcion"


_cuota_edit_store: StateStore[PendingCuotaEditField] = StateStore(
    "cuota_edit", ttl=_REDIS_TTL_SHORT,
)


def set_cuota_edit_field(user_id: int, state: PendingCuotaEditField) -> None:
    _cuota_edit_store.set(user_id, state)


def get_cuota_edit_field(user_id: int) -> PendingCuotaEditField | None:
    return _cuota_edit_store.get(user_id)


def clear_cuota_edit_field(user_id: int) -> None:
    _cuota_edit_store.clear(user_id)


# ── Cuota create state ────────────────────────────────────────────────────────


@dataclass
class PendingCuotaCreate:
    actividad_id: int
    actividad_nombre: str
    step: Literal["await_numbers"]
    grade_id: int
    grade_name: str
    student_list: list[dict]  # [{"idx": int, "student_id": int, "name": str}]


_cuota_create_store: StateStore[PendingCuotaCreate] = StateStore(
    "cuota", use_redis=True, ttl=_REDIS_TTL_SHORT,
)


def set_cuota_create(user_id: int, state: PendingCuotaCreate) -> None:
    _cuota_create_store.set(user_id, state)


def get_cuota_create(user_id: int) -> PendingCuotaCreate | None:
    return _cuota_create_store.get(user_id)


def clear_cuota_create(user_id: int) -> None:
    _cuota_create_store.clear(user_id)


# ── Pending pago ──────────────────────────────────────────────────────────────

_pending_pago_store: StateStore[Any] = StateStore("pago", ttl=_REDIS_TTL_SHORT)


def set_pending_pago(user_id: int, data: Any) -> None:
    _pending_pago_store.set(user_id, data)


def get_pending_pago(user_id: int) -> Any | None:
    return _pending_pago_store.get(user_id)


def pop_pending_pago(user_id: int) -> Any | None:
    return _pending_pago_store.pop(user_id)


# ── Pending confirmation state ────────────────────────────────────────────────


@dataclass
class PendingConfirm:
    chat_id: int
    intent: str  # "attendance" | "homework"
    summary: str  # texto legible para mostrar en la confirmación
    data: Any  # AttendanceExtract | HomeworkExtract


_confirm_store: StateStore[PendingConfirm] = StateStore("confirm", ttl=_REDIS_TTL_SHORT)


def set_pending_confirm(user_id: int, pc: PendingConfirm) -> None:
    _confirm_store.set(user_id, pc)


def pop_pending_confirm(user_id: int) -> PendingConfirm | None:
    return _confirm_store.pop(user_id)


def clear_pending_confirm(user_id: int) -> None:
    _confirm_store.clear(user_id)


# ── Legacy cleanup_stale (backward compat for callers) ────────────────────────

def cleanup_stale() -> int:
    """Backward compat wrapper — delegates to cleanup_all_stale()."""
    return cleanup_all_stale()
