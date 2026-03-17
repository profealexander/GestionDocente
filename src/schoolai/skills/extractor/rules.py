"""Rule-based fallback extractor — no LLM required.

Used when the LLM extractor fails or is unavailable.
Handles the most frequent attendance and homework patterns with regex.
Returns None when the input is ambiguous to avoid false positives.
"""

import re
from functools import lru_cache

from schoolai.skills.extractor.schema import (
    AttendanceExtract,
    ExtractionResult,
    HomeworkExtract,
    QueryExtract,
)
from schoolai.skills.utils.text import normalize

# Radon PLR2004: magic numbers extraídos como constantes
_NAME_MIN_LEN = 3
_NAME_MAX_LEN = 50

# ── Query pre-filter — constantes compiladas al nivel de módulo (0 alloc por llamada) ──

# Regex compilados una sola vez
_QUERY_ATT_RE = re.compile(
    r"\b(asistencia|inasistencias?|faltas?)\b", re.IGNORECASE,
)
_QUERY_HW_RE = re.compile(
    r"\b(tareas?|deberes?|actividades?|pendientes?)\b", re.IGNORECASE,
)
_QUERY_TRIGGER_RE = re.compile(
    r"^\s*(ver|dame|muestra|lista|mostrar|que\s+hay|hay|cuantas?|reporte|listado)\b",
    re.IGNORECASE,
)

# Keywords pre-normalizados → frozenset para O(1) lookup
_ATT_KW: frozenset[str] = frozenset(normalize(w) for w in (
    "asistencia", "inasistencia", "inasistencias", "falta", "faltas",
    "atrasos", "justificados", "quien falto", "quién faltó",
))
_HW_KW: frozenset[str] = frozenset(normalize(w) for w in (
    "tareas", "tarea", "actividades", "actividad", "deberes", "pendientes",
))
_TRIGGER_KW: frozenset[str] = frozenset(normalize(w) for w in (
    "ver", "dame", "muestra", "lista", "mostrar", "hay", "cuantas",
    "cuántas", "reporte", "listado",
))

# Grupos de cursos pre-normalizados → O(1) lookup
_COURSE_GROUPS: dict[str, list[str]] = {
    normalize("bachillerato"):      ["1bt", "2bt", "3bt"],
    normalize("basica superior"):   ["8egb", "9egb", "10egb"],
    normalize("basica media"):      ["5egb", "6egb", "7egb"],
    normalize("basica elemental"):  ["2egb", "3egb", "4egb"],
    normalize("egb"):               ["2egb", "3egb", "4egb", "5egb", "6egb",
                                     "7egb", "8egb", "9egb", "10egb"],
    normalize("inicial"):           ["i1", "i2"],
}

# Periodos: tokens normalizados → valor de período (orden importa: más específico primero)
_PERIOD_TOKENS: tuple[tuple[str, str], ...] = (
    (normalize("primer trimestre"),  "trimester_1"),
    (normalize("trimestre 1"),       "trimester_1"),
    (normalize("segundo trimestre"), "trimester_2"),
    (normalize("trimestre 2"),       "trimester_2"),
    (normalize("tercer trimestre"),  "trimester_3"),
    (normalize("trimestre 3"),       "trimester_3"),
    (normalize("semana pasada"),     "last_week"),
    (normalize("esta semana"),       "week"),
    (normalize("semana"),            "week"),
    (normalize("mes pasado"),        "last_month"),
    (normalize("este mes"),          "month"),
    (normalize("mes"),               "month"),
    (normalize("ayer"),              "yesterday"),
    (normalize("hoy"),               "today"),
)

# ── Attendance keywords ───────────────────────────────────────────────────────

_ABSENT_RE = re.compile(
    r"\b(falt[oó]|faltaron|no\s+asisti[oó]|no\s+asistieron"
    r"|no\s+vino|ausente|inasistencia)\b",
    re.IGNORECASE,
)
_LATE_RE = re.compile(
    r"\b(llego?\s+tarde|lleg[oó]\s+tarde|atrasad[ao]|tardi[oó]|atraso)\b", re.IGNORECASE
)
_JUSTIFIED_RE = re.compile(
    r"\b(justificad[ao]|con\s+permiso|permiso\s+m[eé]dico|enferm[ao])\b", re.IGNORECASE
)
_YESTERDAY_RE = re.compile(r"\bayer\b", re.IGNORECASE)
_ALL_PRESENT_RE = re.compile(
    r"\b(todos\s+asistieron|asistieron\s+todos|todos\s+presentes?|nadie\s+falt[oó]"
    r"|todos\s+vinieron|sin\s+ausencias?|asistencia\s+completa)\b",
    re.IGNORECASE,
)

# ── Homework keywords ─────────────────────────────────────────────────────────

_HW_RE = re.compile(
    r"\b(tarea|deberes?|trabajo\s+pr[aá]ctico|ejercicio|actividad|"
    r"leer|lectura|traer|entregar|evaluaci[oó]n|examen|investigaci[oó]n)\b",
    re.IGNORECASE,
)

# ── Course extraction ─────────────────────────────────────────────────────────

_COURSE_RE = re.compile(
    r"\b(\d{1,2}(?:bt|egb)|prep|i[12])\b",
    re.IGNORECASE,
)

_COURSE_ALIASES: dict[str, str] = {
    "1bt": "1bt", "2bt": "2bt", "3bt": "3bt",
    "2egb": "2egb", "3egb": "3egb", "4egb": "4egb",
    "5egb": "5egb", "6egb": "6egb", "7egb": "7egb",
    "8egb": "8egb", "9egb": "9egb", "10egb": "10egb",
    "prep": "prep", "i1": "i1", "i2": "i2",
}

# Verbal names → abbrev — keys pre-normalizados para comparar contra normalize(text)
_COURSE_VERBAL: dict[str, str] = {
    normalize("primero bt"):    "1bt",   normalize("segundo bt"):  "2bt",
    normalize("tercero bt"):    "3bt",   normalize("segundo egb"): "2egb",
    normalize("tercero egb"):   "3egb",  normalize("cuarto egb"):  "4egb",
    normalize("quinto egb"):    "5egb",  normalize("sexto egb"):   "6egb",
    normalize("septimo egb"):   "7egb",  normalize("octavo egb"):  "8egb",
    normalize("noveno egb"):    "9egb",  normalize("decimo egb"):  "10egb",
    normalize("inicial 1"):     "i1",    normalize("inicial 2"):   "i2",
    normalize("preparatoria"):  "prep",
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_course(text: str) -> str | None:
    """Find course abbreviation via token or verbal match."""
    m = _COURSE_RE.search(text)
    if m:
        return _COURSE_ALIASES.get(m.group(0).lower())
    norm = normalize(text).lower()
    for phrase, abbrev in _COURSE_VERBAL.items():
        if phrase in norm:
            return abbrev
    return None


def _extract_names(text: str, status_re: re.Pattern) -> list[str]:
    """Extract name candidates relative to a status keyword.

    Tries left-of-verb first (most common: "Juan Recalde faltó"),
    then right-of-verb ("Faltó Juan Recalde").
    """
    m = status_re.search(text)
    if not m:
        return []

    left  = text[:m.start()].strip().rstrip(",.")
    # Strip course tokens and trailing prepositions from right side
    right = _COURSE_RE.sub("", text[m.end():]).strip().lstrip(",.")
    right = re.sub(r"\b(en|de|del|para|con)\b", "", right, flags=re.IGNORECASE).strip(", .")

    def _split(segment: str) -> list[str]:
        parts = re.split(r",\s*|\s+y\s+", segment, flags=re.IGNORECASE)
        return [p.strip() for p in parts if _NAME_MIN_LEN <= len(p.strip()) <= _NAME_MAX_LEN]

    candidates = _split(left) or _split(right)

    # Filter out course-like tokens (e.g. "3BT") — not names
    return [c for c in candidates if not _COURSE_RE.fullmatch(c)]


def _first_status_re(text: str) -> tuple[re.Pattern | None, str]:
    """Return the first matching status pattern and its label."""
    # Order matters: justified before late before absent (more specific first)
    for pat, label in (
        (_JUSTIFIED_RE, "justified"),
        (_LATE_RE, "late"),
        (_ABSENT_RE, "absent"),
    ):
        if pat.search(text):
            return pat, label
    return None, "absent"


# ── Helpers para pre-filtro ───────────────────────────────────────────────────

@lru_cache(maxsize=512)
def _norm_tokens(norm_text: str) -> frozenset[str]:
    """Tokens del texto ya normalizado → frozenset para O(1) lookup.
    lru_cache evita re-tokenizar el mismo norm si se reutiliza.
    Recibe norm_text (ya normalizado) para reutilizar el cache de normalize().
    """
    return frozenset(norm_text.split())


def _extract_courses_prefilter(norm_text: str) -> list[str]:
    """Extrae abreviaturas de cursos del texto ya normalizado.

    Orden: verbales > abreviaturas directas > grupos.
    Los verbales y abreviaturas son más específicos que los grupos
    (evita que "noveno egb" devuelva todo EGB en vez de 9egb).
    norm_text debe ser normalize(text) — evita re-normalizar en cada llamada.
    """
    # 1. Nombres verbales (más específicos: "noveno egb" → 9egb)
    found = [abbrev for phrase, abbrev in _COURSE_VERBAL.items() if phrase in norm_text]
    if found:
        return found
    # 2. Abreviaturas directas (1BT, 9EGB, etc.)
    direct = [_COURSE_ALIASES[m.group(0).lower()]
              for m in _COURSE_RE.finditer(norm_text)
              if m.group(0).lower() in _COURSE_ALIASES]
    if direct:
        return direct
    # 3. Grupos (bachillerato, egb, inicial…) — solo si no hay curso específico
    for group_norm, abbrevs in _COURSE_GROUPS.items():
        if group_norm in norm_text:
            return abbrevs
    return []


def _extract_period(norm_text: str, default: str) -> str:
    """Detecta el período en el texto ya normalizado.

    Recorre _PERIOD_TOKENS en orden (más específico primero) y retorna
    el primer match. O(n) sobre una tupla pequeña y constante.
    """
    for token, period in _PERIOD_TOKENS:
        if token in norm_text:
            return period
    return default


# ── Public API ────────────────────────────────────────────────────────────────


def _make_query(query_type: str, norm: str, default_period: str) -> ExtractionResult:
    """Construye ExtractionResult de query. Extrae cursos y período del texto normalizado."""
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


def extract_prefilter(text: str) -> ExtractionResult | None:
    """Pre-filtro de reglas que corre ANTES del LLM para patrones obvios.

    Optimizaciones aplicadas (Ruff/Radon/cProfile):
    - normalize() lru_cache(4096): 1 llamada por mensaje, resultado reutilizado
    - _norm_tokens() lru_cache(512): tokenización cacheada, frozenset O(1)
    - tokens calculados 1 sola vez y reutilizados para att/hw/trigger
    - Regex compilados al módulo: 0 alloc por llamada (re.IGNORECASE)
    - Keywords en frozensets pre-normalizados: intersección O(1)
    - Early-exit por ambigüedad antes de calcular cursos/período
    - Complejidad ciclomática B (Radon) vs C anterior
    - Constantes de nombre al módulo: 0 re-allocations por llamada

    Retorna None si el mensaje es ambiguo → pasar al LLM.
    """
    t = text.strip()
    if not t:
        return None

    # normalize() + _norm_tokens() — cada una llamada 1 sola vez, ambas cacheadas
    norm   = normalize(t)
    tokens = _norm_tokens(norm)

    # Asistencia completa — patrón más específico, antes de queries
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
    is_hw  = bool(_QUERY_HW_RE.search(t))  or bool(tokens & _HW_KW)

    # Ambiguo (ambos tipos presentes) → LLM — early exit antes de calcular trigger
    if is_att and is_hw:
        return None

    if not (is_att or is_hw):
        return None

    trigger = bool(_QUERY_TRIGGER_RE.match(t)) or bool(tokens & _TRIGGER_KW)

    if is_att and (trigger or bool(_QUERY_ATT_RE.match(t))):
        return _make_query("attendance", norm, "today")

    if is_hw and (trigger or bool(_QUERY_HW_RE.match(t))):
        return _make_query("homework", norm, "trimester")

    return None  # sin trigger claro → LLM


def extract_fallback(text: str) -> ExtractionResult | None:
    """Try to extract intent using simple rules.

    Returns ExtractionResult if confident, None if uncertain (let caller decide).
    Does NOT handle query or homework_report — those require LLM context.
    """
    if not text.strip():
        return None

    # ── Asistencia completa ───────────────────────────────────────────────────
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

    # ── Attendance ────────────────────────────────────────────────────────────
    pat, status = _first_status_re(text)
    if pat is not None:
        names  = _extract_names(text, pat)
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

    # ── Homework ──────────────────────────────────────────────────────────────
    if _HW_RE.search(text):
        course = _extract_course(text)
        return ExtractionResult(
            intent="homework",
            data=HomeworkExtract(
                description=text.strip(),
                course=course,
                subject=None,
                delivery_date=None,
                complete=False,   # fallback never provides full info
            ),
        )

    return None   # uncertain — caller should show an error to the user
