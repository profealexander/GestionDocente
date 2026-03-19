"""HomeworkSkill y HWReportSkill — detectan y procesan tareas y cumplimiento."""

from __future__ import annotations

import re

from schoolai.skills.base import BaseSkill
from schoolai.skills.utils.text import normalize


class HomeworkSkill(BaseSkill):
    """Detecta: registro de nuevas tareas / deberes / evaluaciones."""

    intent = "homework"

    keywords: frozenset[str] = frozenset(normalize(w) for w in (
        "tarea", "tareas", "deber", "deberes",
        "actividad", "actividades",
        "evaluacion", "examen", "quiz",
        "investigacion", "lectura", "ejercicio",
    ))

    patterns: list[re.Pattern] = [
        re.compile(
            r"\b(tarea|deberes?|trabajo\s+pr[aá]ctico|ejercicio|actividad|"
            r"leer|lectura|traer|entregar|evaluaci[oó]n|examen|investigaci[oó]n)\b",
            re.IGNORECASE,
        )
    ]

    def matches(self, text: str) -> bool:
        # No capturar si parece un reporte de cumplimiento
        _REPORT_RE = re.compile(
            r"\b(no\s+entreg[oó]|no\s+cumpli[oó]|no\s+trajo|falt[oó]\s+entregar"
            r"|quién?\s+no|quien\s+no|cumplimiento)\b",
            re.IGNORECASE,
        )
        if _REPORT_RE.search(text):
            return False
        return super().matches(text)

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.skills.utils.extract_llm import extract
        from schoolai.skills.utils.extract_rules import extract_prefilter, extract_fallback
        from schoolai.bot.action_handler import handle_extraction

        result = extract_prefilter(text)
        if result is None or result.intent != "homework":
            result = await extract(text, [])
        if result is None or result.intent != "homework":
            result = extract_fallback(text)
        if result is None or result.intent != "homework":
            await update.message.reply_text(
                "No pude interpretar la tarea.\n"
                "_Ejemplo: Tarea de Matemáticas: pág 45 ejercicios 1-5, para 3ro BT_",
                parse_mode="Markdown",
            )
            return
        await handle_extraction(update, user_id, result)


class HWReportSkill(BaseSkill):
    """Detecta: reporte de estudiantes que no entregaron / cumplimiento."""

    intent = "homework_report"

    keywords: frozenset[str] = frozenset(normalize(w) for w in (
        "no entrego", "no cumplió", "no cumplio",
        "no trajo", "cumplimiento",
        "quien no", "quién no",
    ))

    patterns: list[re.Pattern] = [
        re.compile(
            r"\b(no\s+entreg[oó]|no\s+cumpli[oó]|no\s+trajo"
            r"|falt[oó]\s+entregar|quién?\s+no\s+entreg"
            r"|cumplimiento)\b",
            re.IGNORECASE,
        )
    ]

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.skills.utils.extract_llm import extract
        from schoolai.bot.action_handler import handle_extraction

        result = await extract(text, [])
        if result is None or result.intent != "homework_report":
            await update.message.reply_text(
                "No pude interpretar el reporte.\n"
                "_Ejemplo: Recalde y García no entregaron la tarea #2 de 3ro BT_",
                parse_mode="Markdown",
            )
            return
        await handle_extraction(update, user_id, result)
