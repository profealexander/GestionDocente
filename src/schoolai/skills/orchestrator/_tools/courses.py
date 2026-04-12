"""Tool de listado de cursos."""

from __future__ import annotations

from sqlalchemy import select

from schoolai.db.connection import get_db_session
from schoolai.db.models.grade import Grade


async def _list_courses(level: str | None = None) -> str:
    """Lists available courses, optionally filtered by education level."""
    level_aliases = {
        "basica": "egb",
        "básica": "egb",
        "general": "egb",
        "educacion": "egb",
        "educación": "egb",
    }

    async with get_db_session() as session:
        stmt = select(Grade).order_by(Grade.sort_order)
        grades = (await session.execute(stmt)).scalars().all()

    if level:
        db_level = level_aliases.get(level.lower(), level.lower())
        grades = [g for g in grades if (g.level or "").lower() == db_level]

    if not grades:
        suffix = f" de nivel '{level}'" if level else ""
        return f"No se encontraron cursos{suffix}."

    lines = [f"Cursos disponibles{f' ({level})' if level else ''}:"]
    lines.extend(f"  {g.name}" for g in grades)
    return "\n".join(lines)
