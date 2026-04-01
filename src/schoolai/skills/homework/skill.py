"""HomeworkSkill y HWReportSkill — detectan y procesan tareas y cumplimiento."""

from __future__ import annotations

import re

from schoolai.skills.base import BaseSkill
from schoolai.skills.utils.text import normalize


class HomeworkSkill(BaseSkill):
    """Detecta: registro de nuevas tareas / deberes / evaluaciones."""

    intent = "homework"
    priority = 30

    keywords: frozenset[str] = frozenset(
        normalize(w)
        for w in (
            "tarea",
            "tareas",
            "deber",
            "deberes",
            "actividad",
            "actividades",
            "evaluacion",
            "examen",
            "quiz",
            "investigacion",
            "lectura",
            "ejercicio",
        )
    )

    patterns: list[re.Pattern] = [
        re.compile(
            r"\b(tarea|deberes?|trabajo\s+pr[aá]ctico|ejercicio|actividad|"
            r"leer|lectura|traer|entregar|evaluaci[oó]n|examen|investigaci[oó]n)\b",
            re.IGNORECASE,
        ),
    ]

    _REPORT_RE: re.Pattern = re.compile(
        r"\b(no\s+entreg[oó]|no\s+cumpli[oó]|no\s+trajo|falt[oó]\s+entregar"
        r"|quién?\s+no|quien\s+no|cumplimiento)\b",
        re.IGNORECASE,
    )

    # Patrones exclusivos de CuotaSkill — HomeworkSkill no debe interferir
    _CUOTA_EXCLUDE_RE: re.Pattern = re.compile(
        r"\b(listado?\s+(?:de\s+)?actividades?|ver\s+actividades?|listar\s+actividades?"
        r"|actividades?\s+activas?|nueva\s+(?:actividad|cuota)|crear\s+(?:actividad|cuota)"
        r"|cuotas?|pago\s+cuota|exportar\s+cuota)\b",
        re.IGNORECASE,
    )

    # Mensajes que son consultas puras: "tareas" + solo curso/período, sin descripción real
    # Plural "tareas" sola o con filtro corto → es consulta, no creación.
    # Singular "tarea" sin trigger explícito → puede ser creación, no bloquear.
    _QUERY_NOUN_RE: re.Pattern = re.compile(
        # "tareas", "mis tareas", "tareas 3bt", "tareas del trimestre"
        r"^\s*(mis\s+)?tareas\s*(?:(?:de\s+)?(?:\w+\s*){0,3})?\s*$"
        # "tarea #3" — referencia a tarea específica
        r"|^\s*tarea\s*#?\d+\b"
        # "muéstrame / ver / listado + tareas/deberes"
        r"|^\s*(ver|dame|mu[eé]str[ae](me)?|lista(do)?|mostrar|reporte)"
        r"\b.{0,40}(tareas?|taras?|deberes?)\b",
        re.IGNORECASE,
    )

    def matches(self, text: str) -> bool:
        if self._REPORT_RE.search(text):
            return False
        if self._CUOTA_EXCLUDE_RE.search(text):
            return False
        if self._QUERY_NOUN_RE.match(text):
            return False  # es consulta, no creación
        return super().matches(text)

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.bot.action_handler import handle_extraction
        from schoolai.bot.state import get_jornada_context
        from schoolai.skills.homework.detector import (
            extract_course,
            extract_date,
            extract_subject_from_aliases,
            extract_subject_phrase,
            extract_subjects,
        )
        from schoolai.skills.homework.tools import llm_fallback
        from schoolai.skills.utils.schema import ExtractionResult, HomeworkExtract

        course = extract_course(text)
        subjects = extract_subjects(text)
        subject = subjects[0] if subjects else None
        delivery = extract_date(text)

        # Descartar cursos que sean solo dígitos (ej. "9" en "tarea 9") —
        # son falsos positivos del patrón de números EGB sin sufijo.
        if course is not None and re.fullmatch(r"\d{1,2}", course.strip()):
            course = None

        # Extraer descripción real: texto después de ":" si existe
        colon_idx = text.find(":")
        if colon_idx != -1:
            after = text[colon_idx + 1:].strip()
            description = after if after else text.strip()
        else:
            description = text.strip()

        # Si no se reconoció materia por regex, intentar extracción estructural
        if subject is None:
            phrase = extract_subject_phrase(text)
            if phrase:
                subject = phrase
                subjects = [phrase]

        # Tercer fallback: buscar alias conocidos en el texto completo
        if subject is None:
            alias_match = extract_subject_from_aliases(text)
            if alias_match:
                subject = alias_match
                subjects = [alias_match]

        # Completar con contexto de jornada ANTES del LLM — evita alucinaciones
        if not course or not subject:
            _, grade_name, _, subject_name = get_jornada_context(user_id)
            if grade_name and not course:
                course = grade_name
            if subject_name and not subject:
                subject = subject_name
                subjects = [subject_name]

        # Si se menciona "materias" (plural), puede haber múltiples → forzar LLM
        multi_hint = bool(re.search(r"\bmaterias\b", text, re.IGNORECASE))

        result = ExtractionResult(
            intent="homework",
            data=HomeworkExtract(
                description=description,
                course=course,
                subject=subject,
                subjects=subjects,
                delivery_date=delivery.isoformat() if delivery else None,
                complete=bool(course and not multi_hint),
            ),
        )
        # Si la extracción local sigue incompleta, intentar con LLM
        if not result.data.complete:
            llm_result = await llm_fallback(text)
            if llm_result and llm_result.intent == "homework" and llm_result.data.complete:
                llm_result.via_llm = True
                result = llm_result
        await handle_extraction(update, user_id, result)


class HWEditSkill(BaseSkill):
    """Detecta: edición de tareas existentes."""

    intent = "homework_edit"
    priority = 40

    keywords: frozenset[str] = frozenset(
        normalize(w) for w in ("editar", "modificar", "actualizar")
    )

    patterns: list[re.Pattern] = [
        # "editar tarea", "modificar tarea #3", etc.
        re.compile(
            r"\b(editar|modificar|actualizar|cambiar)\b.{0,25}\btarea\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\btarea\b.{0,25}\b(editar|modificar|actualizar|cambiar)\b",
            re.IGNORECASE,
        ),
        # Solo "editar" / "modificar" sin más contexto específico → editar tarea
        re.compile(
            r"^\s*(editar|modificar|actualizar)\s*(\w+\s*){0,3}\s*$",
            re.IGNORECASE,
        ),
    ]

    _OTHER_DOMAIN_RE: re.Pattern = re.compile(
        r"\b(asistencia|falta|atraso|justificado|cuota|actividad|pago)\b",
        re.IGNORECASE,
    )

    def matches(self, text: str) -> bool:
        if self._OTHER_DOMAIN_RE.search(text):
            return False
        return super().matches(text)

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.bot.state import get_jornada_context
        from schoolai.skills.homework.detector import extract_course
        from schoolai.skills.homework.handler_edit import handle_hw_edit

        course = extract_course(text)
        # Descartar bare digits (falsos positivos del detector)
        if course is not None and re.fullmatch(r"\d{1,2}", course.strip()):
            course = None

        ref_m = re.search(r"#?\s*(\d+)", text)
        hw_ref = int(ref_m.group(1)) if ref_m else None

        # Completar con contexto de jornada si no se detectó curso/materia
        subject_id_ctx: int | None = None
        if not course:
            _, grade_name, subject_id_ctx, _ = get_jornada_context(user_id)
            if grade_name:
                course = grade_name

        await handle_hw_edit(update, user_id, course, hw_ref, subject_id=subject_id_ctx)


class HWReportSkill(BaseSkill):
    """Detecta: reporte de estudiantes que no entregaron / cumplimiento."""

    intent = "homework_report"
    priority = 20

    keywords: frozenset[str] = frozenset(
        normalize(w)
        for w in (
            "no entrego",
            "no cumplió",
            "no cumplio",
            "no trajo",
            "cumplimiento",
            "quien no",
            "quién no",
        )
    )

    patterns: list[re.Pattern] = [
        re.compile(
            r"\b(no\s+entreg[oó]|no\s+cumpli[oó]|no\s+trajo"
            r"|falt[oó]\s+entregar|quién?\s+no\s+entreg"
            r"|cumplimiento)\b",
            re.IGNORECASE,
        ),
    ]

    async def handle(self, update, user_id: int, text: str) -> None:
        from schoolai.bot.action_handler import handle_extraction
        from schoolai.skills.homework.detector import extract_course, extract_subject
        from schoolai.skills.homework.tools import llm_fallback
        from schoolai.skills.utils.schema import ExtractionResult, HomeworkReportExtract

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
            left = text[: m.start()].strip().rstrip(",.")
            if len(left) > 2:
                _COURSE_TOK = re.compile(r"\b(\d{1,2}(?:bt|egb)|prep|i[12])\b", re.IGNORECASE)
                _NOISE = {"hoy", "ayer", "el", "la", "los", "las", "de", "del", "al", "para"}
                parts = re.split(r",\s*|\s+y\s+", left, flags=re.IGNORECASE)
                names = [
                    p.strip()
                    for p in parts
                    if p.strip()
                    and len(p.strip()) > 2
                    and p.strip().lower() not in _NOISE
                    and not _COURSE_TOK.fullmatch(p.strip())
                ]

        ref_m = re.search(r"\b(?:tarea|la|#)\s*#?(\d+)\b", text, re.IGNORECASE)
        homework_ref = int(ref_m.group(1)) if ref_m else None

        course = extract_course(text)
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
                llm_result.via_llm = True
                result = llm_result
        await handle_extraction(update, user_id, result)
