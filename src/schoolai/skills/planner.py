"""Planner mínimo — solo se activa cuando detect_all() detecta 2+ skills.

Responsabilidad:
  1. Dividir el texto en fragmentos por conjunciones/puntuación
  2. Asignar cada fragmento a la skill que lo reconoce
  3. Devolver un plan [(skill, fragment), ...] para ejecución secuencial

No usa LLM — puro regex. Si el split no produce asignaciones claras,
cada skill recibe el texto completo (comportamiento conservador).
"""

from __future__ import annotations

import re

from loguru import logger

# Separadores que indican cambio de intención en el mismo mensaje
_SPLIT_RE = re.compile(
    r"\s*[;]\s*"  # punto y coma
    r"|\s+(?:y\s+además|además)\s+"  # "y además", "además"
    r"|\s+también\s+"  # "también"
    r"|\s*,\s*(?=\w)"  # coma seguida de palabra
    r"|\s+y\s+",  # " y " — más genérico, al final
    re.IGNORECASE,
)


def _split_fragments(text: str) -> list[str]:
    """Divide el texto en fragmentos por conjunciones/puntuación."""
    parts = _SPLIT_RE.split(text)
    return [p.strip() for p in parts if len(p.strip()) > 5]


def plan(text: str, skills: list) -> list[tuple]:
    """Asigna fragmentos de texto a skills.

    Args:
        text:   mensaje original del usuario
        skills: lista de BaseSkill detectadas por detect_all()

    Returns:
        Lista de (skill, fragment) en orden de ejecución.
        Si no se puede dividir limpiamente, cada skill recibe el texto completo.
    """
    fragments = _split_fragments(text)

    # Sin split posible → texto completo a cada skill
    if len(fragments) < 2:
        logger.debug(f"[planner] no split → texto completo a {[s.intent for s in skills]}")
        return [(s, text) for s in skills]

    logger.debug(f"[planner] fragmentos={fragments}")

    result: list[tuple] = []
    assigned_intents: set[str] = set()

    for fragment in fragments:
        for skill in skills:
            if skill.intent not in assigned_intents and skill.matches(fragment):
                result.append((skill, fragment))
                assigned_intents.add(skill.intent)
                break

    # Skills no asignadas por el split → texto completo como fallback
    for skill in skills:
        if skill.intent not in assigned_intents:
            logger.debug(f"[planner] skill {skill.intent} sin fragmento → texto completo")
            result.append((skill, text))

    logger.info(f"[planner] plan={[(s.intent, f[:40]) for s, f in result]}")
    return result
