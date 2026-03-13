"""Detect attendance messages and extract names + status from free text."""

import re
import unicodedata
from difflib import SequenceMatcher

FUZZY_THRESHOLD = 0.82  # minimum similarity for keyword fuzzy match

ABSENCE_KEYWORDS = [
    "faltaron", "faltó", "falto", "falta", "ausente", "ausentes",
    "no vino", "no vinieron", "no asistió", "no asistio",
    "no fue", "no fueron", "inasistencia",
]

LATE_KEYWORDS = [
    "tardó", "tardo", "tardanza", "llegó tarde", "llego tarde",
    "llegaron tarde", "atraso", "atrasado", "atrasados", "atrasada",
]

JUSTIFIED_KEYWORDS = [
    "justificado", "justificados", "justificada", "justificadas",
    "con permiso", "permiso", "justificaron", "justificó", "justifico",
]

ALL_KEYWORDS = JUSTIFIED_KEYWORDS + LATE_KEYWORDS + ABSENCE_KEYWORDS

# Words that are keywords themselves — strip from name fragments
KEYWORD_NOISE = {
    _w for kw in ALL_KEYWORDS for _w in kw.split()
} | {
    "llego", "llegar", "esta", "estuvo",
}

# General noise words
NOISE_WORDS = {
    "hoy", "ayer", "el", "la", "los", "las", "de", "del",
    "al", "un", "una", "por", "con", "que", "se", "son",
    "esta", "estan", "curso", "grado", "no",
    # course tokens
    "bt", "bachi", "bachillerato", "egb", "inicial", "preparatoria",
    # verbs
    "vino", "fue", "asistio",
    # grade names
    "segundo", "tercero", "cuarto", "quinto", "sexto", "septimo", "octavo",
    "noveno", "decimo", "primero", "primer",
} | KEYWORD_NOISE

# Separators between names
NAME_SEP_RE = re.compile(r"\s*(?:,|;|\sy\s|\se\s)\s*")

# Course-like tokens e.g. "3ro", "1ro", "2do"
COURSE_TOKEN_RE = re.compile(r"^\d+[a-záéíóú°]*$", re.IGNORECASE)


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def is_attendance_message(text: str) -> bool:
    """Exact keyword match."""
    t = _normalize(text)
    return any(re.search(rf"\b{re.escape(kw)}\b", t) for kw in ALL_KEYWORDS)


def is_attendance_message_fuzzy(text: str) -> bool:
    """Fuzzy match — catches typos like 'faltaon' → 'faltaron'."""
    words = _normalize(text).split()
    # Only single-word keywords for fuzzy (multi-word like "no vino" need exact)
    single_kws = [kw for kw in ALL_KEYWORDS if " " not in kw]
    for word in words:
        if len(word) < 4:  # skip short words to avoid false positives
            continue
        for kw in single_kws:
            if SequenceMatcher(None, word, kw).ratio() >= FUZZY_THRESHOLD:
                return True
    return False


def extract_absences(text: str) -> list[dict]:
    """Return list of {"name": str, "status": "F"|"AT"|"J"} extracted from text."""
    t_lower = _normalize(text)
    results: list[dict] = []
    seen: set[str] = set()

    # Find all keyword positions with their status
    # Order: J > AT > F so higher priority wins on overlap
    keyword_groups = [
        (JUSTIFIED_KEYWORDS, "J"),
        (LATE_KEYWORDS, "AT"),
        (ABSENCE_KEYWORDS, "F"),
    ]

    spans: list[tuple[int, int, str]] = []  # (kw_start, kw_end, status)
    for keywords, status in keyword_groups:
        for kw in keywords:
            for m in re.finditer(rf"\b{re.escape(kw)}\b", t_lower):
                spans.append((m.start(), m.end(), status))

    if not spans:
        return []

    spans.sort(key=lambda x: x[0])

    for i, (kw_start, kw_end, status) in enumerate(spans):
        next_kw_start = spans[i + 1][0] if i + 1 < len(spans) else len(text)

        # Text AFTER keyword (most common: "faltaron Juan, María")
        after = text[kw_end:next_kw_start].strip()
        after = re.split(r"[.!?\n]", after)[0]
        after = re.sub(r"^[\s:,;]+", "", after)
        _extract_names(after, status, seen, results)

        # Text BEFORE keyword on same clause (handles: "Juan llegó tarde")
        # Take up to previous keyword end or sentence start
        prev_end = spans[i - 1][1] if i > 0 else 0
        before = text[prev_end:kw_start].strip()
        before = re.split(r"[.!?\n]", before)[-1]  # last sentence fragment
        before = re.sub(r"[\s:,;]+$", "", before)
        _extract_names(before, status, seen, results)

    return results


def _extract_names(fragment: str, status: str, seen: set, results: list) -> None:
    if not fragment.strip():
        return
    for raw in NAME_SEP_RE.split(fragment):
        name = _clean_name(raw)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            results.append({"name": name, "status": status})


def _clean_name(raw: str) -> str:
    raw = re.sub(r"[^\w\sáéíóúüñÁÉÍÓÚÜÑ]", " ", raw).strip()
    words = [
        w for w in raw.split()
        if _normalize(w) not in NOISE_WORDS
        and len(w) > 1
        and not COURSE_TOKEN_RE.match(w)
    ]
    return " ".join(w.capitalize() for w in words)
