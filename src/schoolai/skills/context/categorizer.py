"""Categorización automática de documentos via LLM.

Determina: título, categoría y scope a partir del contenido + pista opcional.
Usa structured output portable (json_object + Pydantic) en lugar de regex frágil.
"""

from __future__ import annotations

from typing import Literal

from loguru import logger
from pydantic import BaseModel


class _CategorizerOutput(BaseModel):
    title: str
    category: Literal["schedule", "calendar", "policies", "contacts", "notes", "other"]
    scope: Literal["personal", "institution"]


_SYSTEM = """\
You analyze school documents and classify them.
- title: descriptive title, max 70 chars, in the document's language.
- category: best match — schedule (teacher timetable), calendar (school dates/trimesters), \
policies (rules/circulars), contacts (directories/phones), notes (personal notes/reminders), \
other (none of the above).
- scope: personal = specific to one teacher; institution = applies to the whole school.\
"""


async def categorize(content: str, hint: str | None = None) -> dict[str, str]:
    """Retorna {title, category, scope}. Usa defaults si el LLM falla."""
    from schoolai.config import settings
    from schoolai.skills.llm.structured import llm_structured_output

    prompt = (
        f"User hint: {hint or 'none'}\n\n"
        f"Document content (first 2000 chars):\n{content[:2000]}"
    )

    # Intento con el extractor configurado; si el provider falla, structured_output
    # retorna None y usamos el fallback de abajo.
    provider_model = settings.llm_extractor
    result = await llm_structured_output(
        prompt=prompt,
        model_cls=_CategorizerOutput,
        provider_model=provider_model,
        system_prefix=_SYSTEM,
        timeout=20.0,
        agent="context_categorizer",
    )

    if result is None:
        logger.warning("[categorizer] LLM categorization failed, using defaults")
        return {
            "title": hint[:70] if hint else "Documento sin título",
            "category": "other",
            "scope": "personal",
        }

    return {
        "title": result.title[:120],
        "category": result.category,
        "scope": result.scope,
    }
