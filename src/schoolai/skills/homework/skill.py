"""HomeworkSkill y HWReportSkill — detectan y procesan tareas y cumplimiento."""

from __future__ import annotations

import re

from schoolai.skills.base import BaseSkill
from schoolai.skills.utils.text import normalize


class HomeworkSkill(BaseSkill):
    """Detecta: registro de nuevas tareas / deberes / evaluaciones."""

    intent = "homework"
    priority = 30

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

    _REPORT_RE: re.Pattern = re.compile(
        r"\b(no\s+entreg[oó]|no\s+cumpli[oó]|no\s+trajo|falt[oó]\s+entregar"
        r"|quién?\s+no|quien\s+no|cumplimiento)\b",
        re.IGNORECASE,
    )

    def matches(self, text: str) -> bool:
        if self._REPORT_RE.search(text):
            return False
        return super().matches(text)

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.skills.homework.detector import extract_course, extract_subject, extract_date
        from schoolai.skills.homework.tools import llm_fallback
        from schoolai.skills.utils.schema import ExtractionResult, HomeworkExtract
        from schoolai.bot.action_handler import handle_extraction

        course   = extract_course(text)
        subject  = extract_subject(text)
        delivery = extract_date(text)
        result   = ExtractionResult(
            intent="homework",
            data=HomeworkExtract(
                description=text.strip(),
                course=course,
                subject=subject,
                delivery_date=delivery.isoformat() if delivery else None,
                complete=bool(course and subject),
            ),
        )
        # Si la extracción local es incompleta, intentar con LLM
        if not result.data.complete:
            llm_result = await llm_fallback(text)
            if llm_result and llm_result.intent == "homework" and llm_result.data.complete:
                result = llm_result
        await handle_extraction(update, user_id, result)


class HWReportSkill(BaseSkill):
    """Detecta: reporte de estudiantes que no entregaron / cumplimiento."""

    intent = "homework_report"
    priority = 20

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
        from schoolai.skills.homework.detector import extract_course, extract_subject
        from schoolai.skills.homework.tools import llm_fallback
        from schoolai.skills.utils.schema import ExtractionResult, HomeworkReportExtract
        from schoolai.bot.action_handler import handle_extraction

        if re.search(r"\b(tarde|atrasad[ao])\b", text, re.IGNORECASE):
            status = "late"
        elif re.search(r"\b(incompleto|parcial)\b", text, re.IGNORECASE):
            status = "partial"
        else:
            status = "missing"

        _MISS_RE = re.compile(
            r"\b(no\s+entreg[oó]|no\s+cumpli[oó]|no\s+trajo|falt[oó]\s+entregar)\b",
            re.IGNORECASE,
        )
        names: list[str] = []
        m = _MISS_RE.search(text)
        if m:
            left = text[:m.start()].strip().rstrip(",.")
            if len(left) > 2:
                _COURSE_TOK = re.compile(r"\b(\d{1,2}(?:bt|egb)|prep|i[12])\b", re.IGNORECASE)
                _NOISE = {"hoy", "ayer", "el", "la", "los", "las", "de", "del", "al", "para"}
                parts = re.split(r",\s*|\s+y\s+", left, flags=re.IGNORECASE)
                names = [
                    p.strip() for p in parts
                    if p.strip() and len(p.strip()) > 2
                    and p.strip().lower() not in _NOISE
                    and not _COURSE_TOK.fullmatch(p.strip())
                ]

        ref_m = re.search(r"\b(?:tarea|la|#)\s*#?(\d+)\b", text, re.IGNORECASE)
        homework_ref = int(ref_m.group(1)) if ref_m else None

        course  = extract_course(text)
        subject = extract_subject(text)

        result = ExtractionResult(
            intent="homework_report",
            data=HomeworkReportExtract(
                names=names,
                homework_ref=homework_ref,
                course=course,
                subject=subject,
                status=status,
                complete=bool(course),
            ),
        )
        if not result.data.complete:
            llm_result = await llm_fallback(text)
            if llm_result and llm_result.intent == "homework_report" and llm_result.data.complete:
                result = llm_result
        await handle_extraction(update, user_id, result)
