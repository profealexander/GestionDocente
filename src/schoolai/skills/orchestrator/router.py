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
# "actividad" NO está en ninguna lista — es ambiguo (tarea o cuota).
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
    "cuotas": [
        r"\bcuota[s]?\b",
        r"\bpag[oó][s]?\b",      # pago, pagó, pagos
        r"\bcobro[s]?\b",
        r"\bdeuda[s]?\b",
    ],
    "repl": [
        r"\bpromedio\b",                                    # promedio de faltas/notas
        r"\bestadístic",                                    # estadísticas
        r"\branking\b",                                     # ranking de asistencia
        r"\banaliz",                                        # analizar, análisis
        r"\bcuántos?\s+(estudiantes?|alumnos?|cursos?)\b",  # cuántos estudiantes hay
        r"\btotal\s+de\s+(estudiantes?|alumnos?|cursos?)\b",# total de estudiantes
        r"\breporte\s+(general|estadístic|completo|total)", # reporte general/estadístico
    ],
    # Nota: mis_cursos / mi_horario NO necesitan patrón aquí —
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
        from schoolai.skills.orchestrator.skill_agents.cuotas import CuotasAgent
        from schoolai.skills.orchestrator.skill_agents.homework import HomeworkAgent
        from schoolai.skills.orchestrator.skill_agents.repl import ReplAgent

        _agents_cache = {
            "attendance": AttendanceAgent(),
            "homework": HomeworkAgent(),
            "cuotas": CuotasAgent(),
            "repl": ReplAgent(),
        }
    return _agents_cache


# ── Función principal ──────────────────────────────────────────────────────────


def route(text: str) -> list[SkillAgentBase]:
    """Clasifica el mensaje a uno o más SkillAgents.

    Evalúa cada dominio independientemente — un mensaje puede activar varios
    (ej: "registra falta de Juan y el pago del paseo" → attendance + cuotas).

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
