"""QuerySkill — detecta consultas de tareas o asistencia existentes."""

from __future__ import annotations

import re

from schoolai.skills.base import BaseSkill
from schoolai.skills.utils.text import normalize


class QuerySkill(BaseSkill):
    """Detecta: ver tareas, ver asistencia, listar, dame, muéstrame…"""

    intent = "query"
    priority = 40

    keywords: frozenset[str] = frozenset(
        normalize(w)
        for w in (
            "ver",
            "dame",
            "muestra",
            "muestrame",
            "lista",
            "mostrar",
            "hay",
            "cuantas",
            "cuántas",
            "reporte",
            "listado",
        )
    )

    _TRIGGER_PAT = (
        r"ver|dame|muéstrame|muestrame|muestra(me)?|"
        r"lista|mostrar|que\s+hay|hay|cuantas?|reporte|listado"
    )

    # El trigger debe ir al inicio del mensaje
    patterns: list[re.Pattern] = [
        re.compile(rf"^\s*({_TRIGGER_PAT})\b", re.IGNORECASE),
    ]

    # Compilados una sola vez a nivel de clase
    _ATT_RE: re.Pattern = re.compile(
        r"\b(asistencias?|aistencias?|asitencias?|asistncias?|asisencia"
        r"|inasistencias?|faltas?)\b",
        re.IGNORECASE,
    )
    _HW_RE: re.Pattern = re.compile(
        r"\b(tareas?|taras?|deberes?|pendientes?)\b", re.IGNORECASE,
    )
    _TRIGGER_RE: re.Pattern = re.compile(
        rf"^\s*({_TRIGGER_PAT})\b",
        re.IGNORECASE,
    )
    # Plural noun solo → consulta ("tareas", "mis tareas", "deberes").
    # Singular "tarea" solo NO activa — puede ser inicio de creación.
    _NOUN_TRIGGER_RE: re.Pattern = re.compile(
        r"^\s*(mis\s+)?(asistencias?|aistencias?|asitencias?|asistncias?|asisencia"
        r"|faltas?|inasistencias?|tareas|deberes)\b",
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
        from schoolai.bot.action_handler import handle_extraction
        from schoolai.bot.state import get_jornada_context
        from schoolai.skills.query.tools import llm_fallback
        from schoolai.skills.utils.extract_rules import extract_prefilter
        from schoolai.skills.utils.schema import ExtractionResult, QueryExtract

        # Jornada activa tiene prioridad total: ignorar LLM y extracción libre
        from schoolai.skills.utils.courses import _NAME_TO_ABBREV, course_abbrev_map
        _, grade_name, _, subject_name = get_jornada_context(user_id)
        if grade_name:
            abbrev = _NAME_TO_ABBREV.get(grade_name.upper())
            if abbrev and abbrev in course_abbrev_map:
                result = extract_prefilter(text)
                query_type = "homework"
                period = "trimester"
                if result and result.intent == "query":
                    query_type = result.data.query_type
                    period = result.data.period
                await handle_extraction(
                    update,
                    user_id,
                    ExtractionResult(
                        intent="query",
                        data=QueryExtract(
                            query_type=query_type,
                            courses=[abbrev],
                            period=period,
                            complete=True,
                            subject=subject_name,
                        ),
                    ),
                )
                return

        result = extract_prefilter(text)
        if result is None or result.intent != "query":
            result = await llm_fallback(text)
        if result is None or result.intent != "query":
            result = ExtractionResult(
                intent="query",
                data=QueryExtract(
                    query_type="attendance", courses=[], period="today", complete=False,
                ),
            )

        await handle_extraction(update, user_id, result)
