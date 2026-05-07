"""Router de patrones para Bot Agente — clasifica mensajes a SkillAgents.

Nivel 0 (este módulo): patrones regex compilados, costo = 0ms.
  - Solo keywords inequívocos por dominio
  - "actividad" y "atraso en pago" NO están aquí porque son ambiguos
  - 0 matches → _FlatAgent en agent.py (backward compat total)
  - 1 match   → SkillAgent especializado
  - 2+ matches → asyncio.gather de SkillAgents en paralelo

Nivel 1 (Fase 3, no implementado): router LLM para casos ambiguos.
  - Se activaría cuando el texto no hace match en Nivel 0
  - Usa modelo rápido (~150ms) con lista de skills disponibles
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from schoolai.skills.orchestrator.skill_agents.base import SkillAgentBase


# ── Patrones por dominio ───────────────────────────────────────────────────────
#
# Regla: solo keywords que son inequívocos para su dominio.
# "actividad" NO está en ninguna lista — es ambiguo.
# "atraso"    SOLO en attendance — "atraso en pago" queda para _FlatAgent.

_PATTERNS: dict[str, list[str]] = {
    "attendance": [
        r"\bfalt[aoó]",          # falta, falto, faltó, faltas
        r"\bausent[eo]",         # ausente, ausentes, ausento
        r"\batraso",             # atraso (en clase)
        r"\basistencia\b",
        r"\btardanza",
        r"\bjustificad",         # falta justificada
        r"\btodos?\s+present",   # todos presentes
    ],
    "homework": [
        r"\btarea[s]?\b",
        r"\bdeber[es]?\b",
        r"\bexamene?s?\b",       # examen, examenes
        r"\bevaluaci[oó]n",
        r"\bquiz",
        r"\belimin[a]",          # elimina, eliminar tarea
        r"\bborra[r]?\s+tarea",  # borrar tarea
    ],
    "context": [
        # Gestión explícita de documentos
        r"\bdocumento[s]?\s+de\s+contexto\b",
        r"\barchivo[s]?\s+cargado[s]?\b",
        r"\bmi[s]?\s+documento[s]?\b",
        r"\bborrar?\s+(el\s+)?documento\b",
        r"\beliminar?\s+(el\s+)?documento\b",
        r"\blist[ao]r?\s+(mis\s+)?documentos?\b",
        # Consultas sobre contenido de documentos institucionales
        r"\bhorario\s+de\s+(recreo|almuerzo|entrada|salida|clases?)\b",
        r"\bel\s+reglamento\b",
        r"\bel\s+cronograma\b",
        r"\bla\s+normativa\b",
        r"\bel\s+procedimiento\b",
        r"\bqué\s+dice\s+(el|la|un|una)\b",
        r"\bsegún\s+(el|la)\s+(reglamento|cronograma|normativa|documento|circular|manual)\b",
        r"\bcuál\s+es\s+(el\s+horario|la\s+norma|el\s+proceso|el\s+procedimiento)\b",
        r"\bfecha[s]?\s+de\s+(examen|evaluación|inicio|cierre|entrega)\b",
        r"\bcalendario\s+escolar\b",
        r"\bferiado[s]?\b",
        r"\bjornada\s+(laboral|escolar|de\s+trabajo)\b",
        # Búsqueda web explícita
        r"\bbusca[r]?\s+en\s+(internet|la\s+web|google|línea)\b",
        r"\bbusca[r]?\s+información\s+(sobre|de|acerca)\b",
        r"\bencuentra[r]?\s+(en\s+)?(internet|la\s+web)\b",
    ],
    # Nota: my_courses / my_schedule NO necesitan patrón aquí —
    # si no hay match → _FlatAgent, que ya tiene esas tools.
    # Se dejan sin dominio para evitar conflicto con multi-intent paralelo.
}

# Compilación única al importar — búsqueda O(n·k) sin overhead de compilación
_COMPILED: dict[str, list[re.Pattern]] = {
    skill: [re.compile(p, re.IGNORECASE) for p in patterns]
    for skill, patterns in _PATTERNS.items()
}

# ── Singletons de SkillAgents ─────────────────────────────────────────────────

_agents_cache: dict[str, SkillAgentBase] | None = None


def _get_agents() -> dict[str, SkillAgentBase]:
    """Lazy-init de singletons para evitar imports circulares al importar el módulo."""
    global _agents_cache
    if _agents_cache is None:
        from schoolai.skills.orchestrator.skill_agents.attendance import AttendanceAgent
        from schoolai.skills.orchestrator.skill_agents.context import ContextAgent
        from schoolai.skills.orchestrator.skill_agents.homework import HomeworkAgent

        _agents_cache = {
            "attendance": AttendanceAgent(),
            "homework": HomeworkAgent(),
            "context": ContextAgent(),
        }
    return _agents_cache


# ── Función principal ──────────────────────────────────────────────────────────


def route(text: str) -> list[SkillAgentBase]:
    """Clasifica el mensaje a uno o más SkillAgents.

    Evalúa cada dominio independientemente — un mensaje puede activar varios
    (ej: "registra falta de Juan y tarea de matemáticas" → attendance + homework).

    Returns:
        Lista de SkillAgents que corresponden al mensaje.
        Lista vacía → el caller debe usar _FlatAgent como fallback.
    """
    agents = _get_agents()
    matched: list[SkillAgentBase] = []

    for skill_name, patterns in _COMPILED.items():
        for pattern in patterns:
            if pattern.search(text):
                matched.append(agents[skill_name])
                break  # un match por skill es suficiente

    logger.debug(
        f"[router] '{text[:60]}' → "
        f"{[a.name for a in matched] if matched else 'flat_agent (fallback)'}"
    )
    return matched
