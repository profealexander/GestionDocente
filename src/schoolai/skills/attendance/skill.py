"""AttendanceSkill — detecta y procesa mensajes de asistencia."""

from __future__ import annotations

import re

from schoolai.skills.base import BaseSkill
from schoolai.skills.utils.text import normalize


class AttendanceSkill(BaseSkill):
    """Detecta: faltas, atrasos, justificados, todos presentes."""

    intent = "attendance"
    priority = 10

    # Keywords normalizados (sin acentos, minúsculas) — detección O(1)
    keywords: frozenset[str] = frozenset(
        normalize(w)
        for w in (
            "falta",
            "faltas",
            "falto",
            "faltaron",
            "atraso",
            "atrasos",
            "atrasado",
            "atrasada",
            "tardio",
            "tardo",
            "justificado",
            "justificada",
            "ausente",
            "ausentes",
            "inasistencia",
            "inasistencias",
        )
    )

    # Patrones adicionales como fallback al keyword check
    patterns: list[re.Pattern] = [
        re.compile(
            r"\b(falt[oó]|faltaron|no\s+asisti[oó]|no\s+asistieron"
            r"|no\s+vino|ausente|inasistencia"
            r"|llego?\s+tarde|lleg[oó]\s+tarde|atrasad[ao]|tardi[oó]|atraso"
            r"|justificad[ao]|con\s+permiso|permiso\s+m[eé]dico|enferm[ao]"
            r"|todos\s+asistieron|asistieron\s+todos|todos\s+presentes?"
            r"|nadie\s+falt[oó]|todos\s+vinieron|sin\s+ausencias?"
            r"|asistencia\s+completa)\b",
            re.IGNORECASE,
        ),
    ]

    async def handle(self, update, user_id: int, text: str) -> None:
        """Extrae datos del mensaje y delega a action_handler._handle_attendance."""
        from schoolai.bot.action_handler import handle_extraction
        from schoolai.skills.attendance.tools import llm_fallback
        from schoolai.skills.utils.extract_rules import extract_fallback, extract_prefilter

        result = extract_prefilter(text)
        # "quien faltó?" y similares → query de asistencia, no registro
        if result is not None and result.intent == "query":
            await handle_extraction(update, user_id, result)
            return
        if result is None or result.intent != "attendance":
            result = extract_fallback(text)
        if result is None or result.intent != "attendance":
            result = await llm_fallback(text)
            if result and result.intent == "attendance":
                result.via_llm = True
        if result is None or result.intent != "attendance":
            await update.message.reply_text(
                "No pude interpretar el mensaje de asistencia.\n"
                "_Ejemplo: Recalde faltó hoy, 3ro BT_",
                parse_mode="Markdown",
            )
            return
        await handle_extraction(update, user_id, result)


class AttendanceEditSkill(BaseSkill):
    """Detecta: edición/corrección de registros de asistencia existentes."""

    intent = "attendance_edit"
    priority = 8  # antes que AttendanceSkill (10) para interceptar ediciones

    keywords: frozenset[str] = frozenset()

    patterns: list[re.Pattern] = [
        re.compile(
            r"\b(editar|modificar|corregir|actualizar)\b.{0,30}\basistencia\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\basistencia\b.{0,30}\b(editar|modificar|corregir)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(corregir|cambiar)\b.{0,20}\b(falta|atraso|justificado)\b",
            re.IGNORECASE,
        ),
    ]

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.skills.attendance.handler_edit import handle_att_edit
        from schoolai.skills.homework.detector import extract_course, extract_date

        course = extract_course(text)
        att_date = extract_date(text)
        await handle_att_edit(update, user_id, course, att_date)
