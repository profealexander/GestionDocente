"""Mapeo canónico de cursos: abreviatura ↔ nombre ↔ grade_id.

Este módulo centraliza los mapas de cursos que antes vivían en
skills/extractor/llm.py.  Importar desde aquí en todos los módulos
que necesiten resolver cursos.
"""

import time

from loguru import logger

# Mapa estático: nombre canónico en BD → abreviatura
_NAME_TO_ABBREV: dict[str, str] = {
    "INICIAL 1": "i1",
    "INICIAL 2": "i2",
    "PREPARATORIA": "prep",
    "SEGUNDO EGB": "2egb",
    "TERCERO EGB": "3egb",
    "CUARTO EGB": "4egb",
    "QUINTO EGB": "5egb",
    "SEXTO EGB": "6egb",
    "SEPTIMO EGB": "7egb",
    "OCTAVO EGB": "8egb",
    "NOVENO EGB": "9egb",
    "DECIMO EGB": "10egb",
    "PRIMERO BT": "1bt",
    "SEGUNDO BT": "2bt",
    "TERCERO BT": "3bt",
}

# abbrev → grade_id, poblado al arrancar el bot con load_course_map()
course_abbrev_map: dict[str, int] = {}
_last_loaded_at: float = 0.0   # time.monotonic() de la última carga
_RELOAD_INTERVAL = 3600        # recargar desde BD si pasó más de 1 hora

# Aliases de grupo → lista de abreviaturas individuales
# El bot muestra un teclado de selección cuando el docente usa un término genérico.
COURSE_GROUP_ALIASES: dict[str, list[str]] = {
    # Bachillerato
    "bachillerato":  ["1bt", "2bt", "3bt"],
    "bachi":         ["1bt", "2bt", "3bt"],
    "bt":            ["1bt", "2bt", "3bt"],
    # Básica superior
    "basica superior":   ["8egb", "9egb", "10egb"],
    "básica superior":   ["8egb", "9egb", "10egb"],
    # Básica media
    "basica media":      ["5egb", "6egb", "7egb"],
    "básica media":      ["5egb", "6egb", "7egb"],
    # Básica elemental
    "basica elemental":  ["2egb", "3egb", "4egb"],
    "básica elemental":  ["2egb", "3egb", "4egb"],
    # Inicial
    "inicial":       ["i1", "i2"],
    # EGB completo
    "egb":           ["2egb", "3egb", "4egb", "5egb", "6egb", "7egb", "8egb", "9egb", "10egb"],
}

# Lookup inverso: abbrev → nombre canónico
_ABBREV_TO_NAME: dict[str, str] = {v: k for k, v in _NAME_TO_ABBREV.items()}


async def load_course_map(*, force: bool = False) -> None:
    """Carga abrev → grade_id desde la BD.

    Llamar al arrancar el bot. Las cargas posteriores son no-op a menos que
    hayan pasado _RELOAD_INTERVAL segundos o se use force=True.
    Esto evita que cursos añadidos/renombrados en BD queden desactualizados
    por el tiempo de vida del proceso (1 h de ventana máxima de staleness).
    """
    import time

    global _last_loaded_at
    if not force and _last_loaded_at and (time.monotonic() - _last_loaded_at) < _RELOAD_INTERVAL:
        return

    from sqlalchemy import select

    from schoolai.db.connection import get_db_session
    from schoolai.db.models.grade import Grade

    async with get_db_session() as session:
        grades = (await session.execute(select(Grade))).scalars().all()
    course_abbrev_map.clear()
    for g in grades:
        abbrev = _NAME_TO_ABBREV.get(g.name)
        if abbrev:
            course_abbrev_map[abbrev] = g.id
    _last_loaded_at = time.monotonic()
    logger.info(f"[courses] course_map cargado: {len(course_abbrev_map)} cursos")


# ── Cursos por docente ─────────────────────────────────────────────────────────

_teacher_abbrevs_cache: dict[int, tuple[set[str], float]] = {}
_TEACHER_CACHE_TTL = 1800  # 30 min — si cambia el horario, se refleja en media hora


async def get_teacher_abbrevs(telegram_id: int) -> set[str] | None:
    """Retorna el set de abreviaturas asignadas al docente, o None si es admin (sin filtro).

    None = admin → ve todos los cursos.
    set vacío = docente sin cursos asignados.
    set con valores = solo esos cursos son visibles para el docente.

    Cacheado 30 min para evitar queries en cada mensaje.
    """
    from schoolai.config import settings

    # Admin nunca es filtrado
    if settings.admin_telegram_id and telegram_id == settings.admin_telegram_id:
        return None

    # Cache hit
    cached = _teacher_abbrevs_cache.get(telegram_id)
    if cached is not None:
        abbrevs, ts = cached
        if time.monotonic() - ts < _TEACHER_CACHE_TTL:
            return abbrevs

    # Query BD
    from sqlalchemy import select

    from schoolai.db.connection import get_db_session
    from schoolai.db.models.teacher import Schedule, Teacher

    try:
        async with get_db_session() as session:
            teacher = (
                await session.execute(
                    select(Teacher).where(Teacher.telegram_id == telegram_id)
                )
            ).scalar_one_or_none()

            if not teacher:
                # Telegram ID no registrado → sin filtro (puede ser un admin sin ID en BD)
                return None

            schedules = (
                await session.execute(
                    select(Schedule).where(
                        Schedule.teacher_id == teacher.id,
                        Schedule.is_active.is_(True),
                    )
                )
            ).scalars().all()
    except Exception as e:
        logger.warning(f"[courses] no se pudieron cargar cursos del docente {telegram_id}: {e}")
        return None

    grade_names = {s.grade.name for s in schedules}
    abbrevs = {_NAME_TO_ABBREV[name] for name in grade_names if name in _NAME_TO_ABBREV}
    _teacher_abbrevs_cache[telegram_id] = (abbrevs, time.monotonic())
    logger.debug(f"[courses] docente={telegram_id} cursos={sorted(abbrevs)}")
    return abbrevs


def invalidate_teacher_cache(telegram_id: int) -> None:
    """Invalida el cache de un docente (llamar si cambia su horario)."""
    _teacher_abbrevs_cache.pop(telegram_id, None)
