"""Categorización automática de documentos via LLM.

Determina: título, categoría y scope a partir del contenido + pista opcional.
"""

from __future__ import annotations

import asyncio
import json
import re

_CATEGORIES = ["schedule", "calendar", "policies", "contacts", "notes", "other"]
_SCOPES = ["personal", "institution"]

_PROMPT = """\
Analiza el siguiente contenido de un documento y determina:
1. Un título descriptivo (máximo 70 caracteres).
2. La categoría más apropiada de esta lista:
   - schedule   → horario del docente (clases, horas, días)
   - calendar   → calendario escolar, cronograma de fechas, trimestres, feriados
   - policies   → reglamentos, normas, circulares, comunicados oficiales
   - contacts   → directorio de contactos, teléfonos, correos
   - notes      → apuntes, recordatorios, notas personales
   - other      → no encaja en ninguna categoría anterior
3. El alcance:
   - personal     → información específica del docente (su horario, sus notas)
   - institution  → aplica a toda la institución (calendario escolar, reglamentos)

Pista del usuario: {hint}

Contenido (primeros 2000 caracteres):
{content}

Responde ÚNICAMENTE con JSON válido, sin texto adicional:
{{"title": "...", "category": "...", "scope": "..."}}
"""


async def categorize(content: str, hint: str | None = None) -> dict[str, str]:
    """Retorna {title, category, scope}. Usa defaults si el LLM falla."""
    from schoolai.config import settings
    from schoolai.skills.llm.client import get_client, parse_model

    provider, model = parse_model(settings.llm_orchestrator)
    try:
        client = get_client(provider, timeout=20.0)
    except ValueError:
        provider, model = parse_model(settings.llm_orchestrator_fallback.split(",")[0].strip())
        client = get_client(provider, timeout=20.0)

    prompt = _PROMPT.format(
        hint=hint or "ninguna",
        content=content[:2000],
    )

    def _call():
        return client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

    try:
        response = await asyncio.to_thread(_call)
        raw = (response.choices[0].message.content or "").strip()
        # Extraer JSON aunque venga envuelto en ```json ... ```
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "title":    str(data.get("title", "Documento"))[:120],
                "category": data.get("category", "other") if data.get("category") in _CATEGORIES else "other",
                "scope":    data.get("scope", "personal") if data.get("scope") in _SCOPES else "personal",
            }
    except Exception:
        pass

    # Fallback: title desde hint o genérico
    return {
        "title":    (hint[:70] if hint else "Documento sin título"),
        "category": "other",
        "scope":    "personal",
    }
