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

    def matches(self, text: str) -> bool:
        """Solo activa si hay un trigger explícito + palabra de asistencia/tarea."""
        _ATT_RE = re.compile(r"\b(asistencia|inasistencias?|faltas?)\b", re.IGNORECASE)
        _HW_RE  = re.compile(r"\b(tareas?|deberes?|actividades?|pendientes?)\b", re.IGNORECASE)
        _TRIGGER_RE = re.compile(
            r"^\s*(ver|dame|muestra|lista|mostrar|que\s+hay|hay|cuantas?|reporte|listado)\b",
            re.IGNORECASE,
        )

        has_trigger = bool(_TRIGGER_RE.match(text))
        if not has_trigger:
            return False
        return bool(_ATT_RE.search(text)) or bool(_HW_RE.search(text))

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.skills.utils.extract_rules import extract_prefilter
        from schoolai.skills.utils.extract_llm import extract
        from schoolai.bot.action_handler import handle_extraction

        result = extract_prefilter(text)
        if result is None or result.intent != "query":
            result = await extract(text, [])
        if result is None or result.intent != "query":
            await update.message.reply_text(
                "No entendí la consulta.\n"
                "_Ejemplo: Ver tareas de 1ro BT esta semana_",
                parse_mode="Markdown",
            )
            return
        await handle_extraction(update, user_id, result)
