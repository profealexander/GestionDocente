"""Mapeo canónico de cursos: abreviatura ↔ nombre ↔ grade_id.

Este módulo centraliza los mapas de cursos que antes vivían en
skills/extractor/llm.py.  Importar desde aquí en todos los módulos
que necesiten resolver cursos.
"""

from loguru import logger

# Mapa estático: nombre canónico en BD → abreviatura
_NAME_TO_ABBREV: dict[str, str] = {
    "INICIAL 1": "i1",    "INICIAL 2": "i2",
    "PREPARATORIA": "prep",
    "SEGUNDO EGB": "2egb", "TERCERO EGB": "3egb",  "CUARTO EGB": "4egb",
    "QUINTO EGB":  "5egb", "SEXTO EGB":   "6egb",  "SEPTIMO EGB": "7egb",
    "OCTAVO EGB":  "8egb", "NOVENO EGB":  "9egb",  "DECIMO EGB":  "10egb",
    "PRIMERO BT":  "1bt",  "SEGUNDO BT":  "2bt",   "TERCERO BT":  "3bt",
}

# abbrev → grade_id, poblado al arrancar el bot con load_course_map()
course_abbrev_map: dict[str, int] = {}

# Lookup inverso: abbrev → nombre canónico
_ABBREV_TO_NAME: dict[str, str] = {v: k for k, v in _NAME_TO_ABBREV.items()}


async def load_course_map() -> None:
    """Carga abrev → grade_id desde la BD. Llamar al arrancar el bot."""
    from sqlalchemy import select
    from schoolai.db.connection import async_session
    from schoolai.db.models.grade import Grade

    async with async_session() as session:
        grades = (await session.execute(select(Grade))).scalars().all()
    for g in grades:
        abbrev = _NAME_TO_ABBREV.get(g.name)
        if abbrev:
            course_abbrev_map[abbrev] = g.id
    logger.info(f"[courses] course_map cargado: {len(course_abbrev_map)} cursos")
