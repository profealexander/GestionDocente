"""QuerySkill — detecta consultas de tareas o asistencia existentes."""

from __future__ import annotations

import re

from schoolai.skills.base import BaseSkill
from schoolai.skills.utils.text import normalize


class QuerySkill(BaseSkill):
    """Detecta: ver tareas, ver asistencia, listar, dame, muéstrame…"""

    intent = "query"

    keywords: frozenset[str] = frozenset(normalize(w) for w in (
        "ver", "dame", "muestra", "lista", "mostrar",
        "hay", "cuantas", "cuántas", "reporte", "listado",
    ))

    # El trigger debe ir al inicio del mensaje — igual que _QUERY_TRIGGER_RE
    patterns: list[re.Pattern] = [
        re.compile(
            r"^\s*(ver|dame|muestra|lista|mostrar|que\s+hay|hay|cuantas?|reporte|listado)\b",
            re.IGNORECASE,
        )
    ]

    # Compilados una sola vez a nivel de clase
    _ATT_RE: re.Pattern = re.compile(r"\b(asistencia|inasistencias?|faltas?)\b", re.IGNORECASE)
    _HW_RE: re.Pattern  = re.compile(r"\b(tareas?|deberes?|actividades?|pendientes?)\b", re.IGNORECASE)
    _TRIGGER_RE: re.Pattern = re.compile(
        r"^\s*(ver|dame|muestra|lista|mostrar|que\s+hay|hay|cuantas?|reporte|listado)\b",
        re.IGNORECASE,
    )
    _NOUN_TRIGGER_RE: re.Pattern = re.compile(
        r"^\s*(asistencias?|asitencias?|asistncias?|tareas?|deberes?|faltas?|inasistencias?)\s+(de|del?)\b",
        re.IGNORECASE,
    )

    def matches(self, text: str) -> bool:
        """Solo activa si hay un trigger explícito + palabra de asistencia/tarea."""
        if self._NOUN_TRIGGER_RE.match(text):
            return True
        if not self._TRIGGER_RE.match(text):
            return False
        return bool(self._ATT_RE.search(text)) or bool(self._HW_RE.search(text))

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.skills.utils.extract_rules import extract_prefilter
        from schoolai.skills.query.tools import llm_fallback
        from schoolai.skills.utils.schema import ExtractionResult, QueryExtract
        from schoolai.bot.action_handler import handle_extraction

        result = extract_prefilter(text)
        if result is None or result.intent != "query":
            result = await llm_fallback(text)
        if result is None or result.intent != "query":
            # Fallback mínimo: pedir curso al usuario
            result = ExtractionResult(
                intent="query",
                data=QueryExtract(query_type="attendance", courses=[], period="today", complete=False),
            )
        await handle_extraction(update, user_id, result)
