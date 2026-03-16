"""Rule-based fallback extractor — no LLM required.

Used when the LLM extractor fails or is unavailable.
Handles the most frequent attendance and homework patterns with regex.
Returns None when the input is ambiguous to avoid false positives.
"""

import re

from schoolai.skills.extractor.schema import (
    AttendanceExtract,
    ChatExtract,
    ExtractionResult,
    HomeworkExtract,
)
from schoolai.skills.utils.text import normalize

# ── Attendance keywords ───────────────────────────────────────────────────────

_ABSENT_RE = re.compile(
    r"\b(falt[oó]|faltaron|no\s+asisti[oó]|no\s+asistieron|no\s+vino|ausente|inasistencia)\b", re.I
)
_LATE_RE = re.compile(
    r"\b(llego?\s+tarde|lleg[oó]\s+tarde|atrasad[ao]|tardi[oó]|atraso)\b", re.I
)
_JUSTIFIED_RE = re.compile(
    r"\b(justificad[ao]|con\s+permiso|permiso\s+m[eé]dico|enferm[ao])\b", re.I
)
_YESTERDAY_RE = re.compile(r"\bayer\b", re.I)

# ── Homework keywords ─────────────────────────────────────────────────────────

_HW_RE = re.compile(
    r"\b(tarea|deberes?|trabajo\s+pr[aá]ctico|ejercicio|actividad|"
    r"leer|lectura|traer|entregar|evaluaci[oó]n|examen|investigaci[oó]n)\b",
    re.I,
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

# Verbal names → abbrev (checked against normalize() output, lowercase no accents)
_COURSE_VERBAL: dict[str, str] = {
    "primero bt": "1bt",    "segundo bt": "2bt",   "tercero bt": "3bt",
    "segundo egb": "2egb",  "tercero egb": "3egb", "cuarto egb": "4egb",
    "quinto egb": "5egb",   "sexto egb": "6egb",   "septimo egb": "7egb",
    "octavo egb": "8egb",   "noveno egb": "9egb",  "decimo egb": "10egb",
    "inicial 1": "i1",      "inicial 2": "i2",     "preparatoria": "prep",
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
    right = re.sub(r"\b(en|de|del|para|con)\b", "", right, flags=re.I).strip(", .")

    def _split(segment: str) -> list[str]:
        parts = re.split(r",\s*|\s+y\s+", segment, flags=re.I)
        return [p.strip() for p in parts if 3 <= len(p.strip()) <= 50]

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


# ── Public API ────────────────────────────────────────────────────────────────


def extract_fallback(text: str) -> ExtractionResult | None:
    """Try to extract intent using simple rules.

    Returns ExtractionResult if confident, None if uncertain (let caller decide).
    Does NOT handle query or homework_report — those require LLM context.
    """
    if not text.strip():
        return None

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
