"""Mapeo canónico de cursos: abreviatura ↔ nombre ↔ grade_id.

Este módulo centraliza los mapas de cursos que antes vivían en
skills/extractor/llm.py.  Importar desde aquí en todos los módulos
que necesiten resolver cursos.
"""

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

    from schoolai.db.connection import async_session
    from schoolai.db.models.grade import Grade

    async with async_session() as session:
        grades = (await session.execute(select(Grade))).scalars().all()
    course_abbrev_map.clear()
    for g in grades:
        abbrev = _NAME_TO_ABBREV.get(g.name)
        if abbrev:
            course_abbrev_map[abbrev] = g.id
    _last_loaded_at = time.monotonic()
    logger.info(f"[courses] course_map cargado: {len(course_abbrev_map)} cursos")
