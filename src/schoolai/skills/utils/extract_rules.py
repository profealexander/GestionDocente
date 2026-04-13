"""Extracción de entidades basada en reglas/regex — sin LLM."""

import re
from datetime import date
from functools import lru_cache

from schoolai.skills.utils.schema import (
    AttendanceExtract,
    ExtractionResult,
    HomeworkExtract,
    QueryExtract,
)
from schoolai.skills.utils.text import normalize

_NAME_MIN_LEN = 3
_NAME_MAX_LEN = 50

# ── Query pre-filter ──────────────────────────────────────────────────────────

_QUERY_ATT_RE = re.compile(
    r"\b(asistencias?|aistencias?|asitencias?|asistncias?|asisencia"
    r"|inasistencias?|faltas?)\b",
    re.IGNORECASE,
)
_QUERY_HW_RE = re.compile(r"\b(tareas?|taras?|deberes?|pendientes?)\b", re.IGNORECASE)
_QUERY_TRIGGER_RE = re.compile(
    r"^\s*(ver|dame|muestra|lista|mostrar|que\s+hay|hay|cuantas?|reporte|listado)\b",
    re.IGNORECASE,
)
# "quien faltó?", "quiénes faltaron?", "quien no asistió?" → attendance query
_QUERY_WHO_RE = re.compile(
    r"^\s*qui[eé]n(es)?\s+(falt[oó]|faltaron|no\s+asisti[oó]|no\s+asistieron"
    r"|no\s+vino|no\s+vinieron|est[aá](n)?\s+ausentes?)\b",
    re.IGNORECASE,
)

_ATT_KW: frozenset[str] = frozenset(
    normalize(w)
    for w in (
        "asistencia",
        "inasistencia",
        "inasistencias",
        "falta",
        "faltas",
        "atrasos",
        "justificados",
        "quien falto",
        "quién faltó",
    )
)
_HW_KW: frozenset[str] = frozenset(
    normalize(w)
    for w in (
        "tareas",
        "tarea",
        "taras",
        "deberes",
        "pendientes",
    )
)
_TRIGGER_KW: frozenset[str] = frozenset(
    normalize(w)
    for w in (
        "ver",
        "dame",
        "muestra",
        "lista",
        "mostrar",
        "hay",
        "cuantas",
        "cuántas",
        "reporte",
        "listado",
    )
)

_COURSE_GROUPS: dict[str, list[str]] = {
    normalize("bachillerato"): ["1bt", "2bt", "3bt"],
    normalize("basica superior"): ["8egb", "9egb", "10egb"],
    normalize("basica media"): ["5egb", "6egb", "7egb"],
    normalize("basica elemental"): ["2egb", "3egb", "4egb"],
    normalize("egb"): ["2egb", "3egb", "4egb", "5egb", "6egb", "7egb", "8egb", "9egb", "10egb"],
    normalize("inicial"): ["i1", "i2"],
}

_PERIOD_TOKENS: tuple[tuple[str, str], ...] = (
    (normalize("primer trimestre"), "trimester_1"),
    (normalize("trimestre 1"), "trimester_1"),
    (normalize("segundo trimestre"), "trimester_2"),
    (normalize("trimestre 2"), "trimester_2"),
    (normalize("tercer trimestre"), "trimester_3"),
    (normalize("trimestre 3"), "trimester_3"),
    (normalize("semana pasada"), "last_week"),
    (normalize("esta semana"), "week"),
    (normalize("semana"), "week"),
    (normalize("mes pasado"), "last_month"),
    (normalize("este mes"), "month"),
    (normalize("mes"), "month"),
    (normalize("ayer"), "yesterday"),
    (normalize("hoy"), "today"),
)

# ── Attendance patterns ───────────────────────────────────────────────────────

_ABSENT_RE = re.compile(
    r"\b(faltas?|falt[oó]|faltaron|no\s+asisti[oó]|no\s+asistieron"
    r"|no\s+vino|ausente|inasistencia)\b",
    re.IGNORECASE,
)
_LATE_RE = re.compile(
    r"\b(llego?\s+tarde|lleg[oó]\s+tarde|atrasad[ao]|tardi[oó]|atraso)\b", re.IGNORECASE,
)
_JUSTIFIED_RE = re.compile(
    r"\b(justificad[ao]|con\s+permiso|permiso\s+m[eé]dico|enferm[ao])\b", re.IGNORECASE,
)
_YESTERDAY_RE = re.compile(r"\bayer\b", re.IGNORECASE)
_ALL_PRESENT_RE = re.compile(
    r"\b(todos\s+asistieron|asistieron\s+todos|todos\s+presentes?|nadie\s+falt[oó]"
    r"|todos\s+vinieron|sin\s+ausencias?|asistencia\s+completa)\b",
    re.IGNORECASE,
)

# ── Homework pattern ──────────────────────────────────────────────────────────

_HW_RE = re.compile(
    r"\b(tarea|deberes?|trabajo\s+pr[aá]ctico|ejercicio|actividad|"
    r"leer|lectura|traer|entregar|evaluaci[oó]n|examen|investigaci[oó]n)\b",
    re.IGNORECASE,
)

# ── Course extraction ─────────────────────────────────────────────────────────

_COURSE_RE = re.compile(r"\b(\d{1,2}(?:bt|egb)|prep|i[12])\b", re.IGNORECASE)

# Verbal course names stripped from name segments: "Primero BT", "Décimo EGB", etc.
_COURSE_VERBAL_RE = re.compile(
    r"\b("
    r"primero?\s+bt|segundo?\s+bt|tercero?\s+bt"
    r"|segundo?\s+egb|tercero?\s+egb|cuarto?\s+egb|quinto?\s+egb"
    r"|sexto?\s+egb|s[eé]ptimo?\s+egb|octavo?\s+egb|noveno?\s+egb|d[eé]cimo?\s+egb"
    r"|inicial\s+[12]|preparatoria"
    r")\b",
    re.IGNORECASE,
)

_PERIOD_OR_COURSE_RE = re.compile(
    r"\b(hoy|ayer|esta\s+semana|semana\s+pasada|este\s+mes|mes\s+pasado|trimestre"
    r"|\d{1,2}(?:bt|egb)|prep|i[12]"
    r"|bachillerato|b[aá]sica|inicial|egb"
    r"|primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|d[eé]cimo)\b",
    re.IGNORECASE,
)

_COURSE_ALIASES: dict[str, str] = {
    "1bt": "1bt",
    "2bt": "2bt",
    "3bt": "3bt",
    "2egb": "2egb",
    "3egb": "3egb",
    "4egb": "4egb",
    "5egb": "5egb",
    "6egb": "6egb",
    "7egb": "7egb",
    "8egb": "8egb",
    "9egb": "9egb",
    "10egb": "10egb",
    "prep": "prep",
    "i1": "i1",
    "i2": "i2",
}

_COURSE_VERBAL: dict[str, str] = {
    normalize("primero bt"): "1bt",
    normalize("segundo bt"): "2bt",
    normalize("tercero bt"): "3bt",
    normalize("segundo egb"): "2egb",
    normalize("tercero egb"): "3egb",
    normalize("cuarto egb"): "4egb",
    normalize("quinto egb"): "5egb",
    normalize("sexto egb"): "6egb",
    normalize("septimo egb"): "7egb",
    normalize("octavo egb"): "8egb",
    normalize("noveno egb"): "9egb",
    normalize("decimo egb"): "10egb",
    normalize("inicial 1"): "i1",
    normalize("inicial 2"): "i2",
    normalize("preparatoria"): "prep",
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_course(text: str) -> str | None:
    m = _COURSE_RE.search(text)
    if m:
        return _COURSE_ALIASES.get(m.group(0).lower())
    norm = normalize(text)
    for phrase, abbrev in _COURSE_VERBAL.items():
        if phrase in norm:
            return abbrev
    return None


def _extract_names(text: str, status_re: re.Pattern) -> list[str]:
    m = status_re.search(text)
    if not m:
        return []
    left = text[: m.start()].strip().rstrip(",.")
    right = _COURSE_RE.sub("", text[m.end() :]).strip().lstrip(",.")
    right = _COURSE_VERBAL_RE.sub("", right).strip(", .")
    right = re.sub(r"\b(en|de|del|para|con)\b", "", right, flags=re.IGNORECASE).strip(", .")

    def _split(segment: str) -> list[str]:
        parts = re.split(r",\s*|\s+y\s+", segment, flags=re.IGNORECASE)
        return [
            p.strip() for p in parts
            if _NAME_MIN_LEN <= len(p.strip()) <= _NAME_MAX_LEN
            and normalize(p.strip()) not in _ATT_KW
        ]

    candidates = _split(left) or _split(right)
    return [c for c in candidates if not _COURSE_RE.fullmatch(c)]


def _first_status_re(text: str) -> tuple[re.Pattern | None, str]:
    for pat, label in (
        (_JUSTIFIED_RE, "justified"),
        (_LATE_RE, "late"),
        (_ABSENT_RE, "absent"),
    ):
        if pat.search(text):
            return pat, label
    return None, "absent"


@lru_cache(maxsize=512)
def _norm_tokens(norm_text: str) -> frozenset[str]:
    return frozenset(norm_text.split())


def _extract_courses_prefilter(norm_text: str) -> list[str]:
    found = [abbrev for phrase, abbrev in _COURSE_VERBAL.items() if phrase in norm_text]
    if found:
        return found
    direct = [
        _COURSE_ALIASES[m.group(0).lower()]
        for m in _COURSE_RE.finditer(norm_text)
        if m.group(0).lower() in _COURSE_ALIASES
    ]
    if direct:
        return direct
    for group_norm, abbrevs in _COURSE_GROUPS.items():
        if group_norm in norm_text:
            return abbrevs
    return []


_DAY_OF_MONTH_RE = re.compile(r"\bdel?\s+(\d{1,2})\b")
_DAY_NAME_RE = re.compile(
    r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\b", re.IGNORECASE,
)
_DAY_NAME_MAP = {
    "lunes": "lunes", "martes": "martes",
    "miercoles": "miercoles", "miércoles": "miercoles",
    "jueves": "jueves", "viernes": "viernes",
    "sabado": "sabado", "sábado": "sabado", "domingo": "domingo",
}


def _extract_period(norm_text: str, default: str) -> str:
    for token, period in _PERIOD_TOKENS:
        if token in norm_text:
            return period
    # "del 17" / "dia 17" → día del mes actual (ISO)
    m = _DAY_OF_MONTH_RE.search(norm_text)
    if m:
        day = int(m.group(1))
        today = date.today()
        try:
            d = today.replace(day=day)
            # Si el día aún no llegó este mes → mes anterior
            if d > today:
                first = today.replace(day=1)
                import calendar
                prev_month = first.replace(
                    day=1,
                    month=first.month - 1 if first.month > 1 else 12,
                    year=first.year if first.month > 1 else first.year - 1,
                )
                last_prev = calendar.monthrange(prev_month.year, prev_month.month)[1]
                d = prev_month.replace(day=min(day, last_prev))
            return d.isoformat()
        except ValueError:
            pass
    # nombre de día (lunes…domingo) → más reciente pasado
    m = _DAY_NAME_RE.search(norm_text)
    if m:
        return m.group(1).lower().replace("é", "e").replace("á", "a")
    return default


def _make_query(query_type: str, norm: str, default_period: str) -> ExtractionResult:
    courses = _extract_courses_prefilter(norm)
    return ExtractionResult(
        intent="query",
        data=QueryExtract(
            query_type=query_type,
            courses=courses,
            period=_extract_period(norm, default_period),
            complete=bool(courses),
            subject=None,
        ),
    )


# ── Public API ────────────────────────────────────────────────────────────────


def extract_prefilter(text: str) -> ExtractionResult | None:
    """Pre-filtro de reglas que corre ANTES del LLM para patrones obvios.
    Retorna None si el mensaje es ambiguo → pasar al LLM.
    """
    t = text.strip()
    if not t:
        return None

    norm = normalize(t)
    tokens = _norm_tokens(norm)

    # "quien faltó?" / "quiénes faltaron?" → attendance query (not registration)
    if _QUERY_WHO_RE.match(t):
        return _make_query("attendance", norm, "today")

    if _ALL_PRESENT_RE.search(t):
        course = _extract_course(t)
        if not course:
            for group_norm in _COURSE_GROUPS:
                if group_norm in norm:
                    course = group_norm
                    break
        at_date = "yesterday" if _YESTERDAY_RE.search(t) else "today"
        return ExtractionResult(
            intent="attendance",
            data=AttendanceExtract(
                names=[],
                course=course,
                date=at_date,
                status="all_present",
                complete=True,
            ),
        )

    is_att = bool(_QUERY_ATT_RE.search(t)) or bool(tokens & _ATT_KW)
    is_hw = bool(_QUERY_HW_RE.search(t)) or bool(tokens & _HW_KW)

    if is_att and is_hw:
        return None
    if not (is_att or is_hw):
        return None

    trigger = bool(_QUERY_TRIGGER_RE.match(t)) or bool(tokens & _TRIGGER_KW)

    has_status_modifier = bool(_JUSTIFIED_RE.search(t)) or bool(_LATE_RE.search(t))

    # Treat "starts with att keyword" as a query when:
    # - a period/course indicator is present: "Faltas de hoy 3BT"
    # - OR the entire message is only att keywords: "asistencia", "faltas"
    # NOT when followed by a name: "Falta tatiana" (registration)
    _pure_att = frozenset(norm.split()) <= _ATT_KW
    is_likely_query_by_start = (
        bool(_QUERY_ATT_RE.match(t))
        and (bool(_PERIOD_OR_COURSE_RE.search(t)) or _pure_att)
        and not has_status_modifier
    )

    if is_att and (trigger or is_likely_query_by_start):
        return _make_query("attendance", norm, "today")
    if is_hw and (trigger or bool(_QUERY_HW_RE.match(t))):
        return _make_query("homework", norm, "trimester")

    return None


def extract_fallback(text: str) -> ExtractionResult | None:
    """Fallback de reglas básicas cuando el LLM falla.
    No maneja query ni homework_report — esos requieren contexto LLM.
    """
    if not text.strip():
        return None

    if _ALL_PRESENT_RE.search(text):
        course = _extract_course(text)
        at_date = "yesterday" if _YESTERDAY_RE.search(text) else "today"
        return ExtractionResult(
            intent="attendance",
            data=AttendanceExtract(
                names=[],
                course=course,
                date=at_date,
                status="all_present",
                complete=True,
            ),
        )

    pat, status = _first_status_re(text)
    if pat is not None:
        names = _extract_names(text, pat)
        course = _extract_course(text)
        at_date = "yesterday" if _YESTERDAY_RE.search(text) else "today"
        if names:
            return ExtractionResult(
                intent="attendance",
                data=AttendanceExtract(
                    names=names,
                    course=course,
                    date=at_date,
                    status=status,
                    complete=course is not None,
                ),
            )

    if _HW_RE.search(text):
        course = _extract_course(text)
        return ExtractionResult(
            intent="homework",
            data=HomeworkExtract(
                description=text.strip(),
                course=course,
                subject=None,
                delivery_date=None,
                complete=False,
            ),
        )

    return None
