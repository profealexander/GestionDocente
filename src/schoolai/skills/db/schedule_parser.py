"""Parse free-text schedule input into structured period dicts.

Expected format (one period per line):
    07:00-08:30 3BT Matemáticas
    08:30-10:00 2BT Física
    10:30-12:00 10EGB Lengua y Literatura
"""

import re
from dataclasses import dataclass


# Maps course abbreviations/aliases → canonical abbrev used in course_abbrev_map
_COURSE_ALIASES: dict[str, str] = {
    # bachillerato
    "1bt": "1bt", "1bachi": "1bt", "primero bt": "1bt", "1°bt": "1bt",
    "2bt": "2bt", "2bachi": "2bt", "segundo bt": "2bt", "2°bt": "2bt",
    "3bt": "3bt", "3bachi": "3bt", "tercero bt": "3bt", "3°bt": "3bt",
    # egb
    "2egb": "2egb", "segundo egb": "2egb", "2°egb": "2egb",
    "3egb": "3egb", "tercero egb": "3egb",
    "4egb": "4egb", "cuarto egb": "4egb",
    "5egb": "5egb", "quinto egb": "5egb",
    "6egb": "6egb", "sexto egb": "6egb",
    "7egb": "7egb", "septimo egb": "7egb",
    "8egb": "8egb", "octavo egb": "8egb",
    "9egb": "9egb", "noveno egb": "9egb",
    "10egb": "10egb", "decimo egb": "10egb",
    "prep": "prep", "preparatoria": "prep",
    "i1": "i1", "inicial 1": "i1",
    "i2": "i2", "inicial 2": "i2",
}

_TIME_RE = re.compile(r"^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})\s+(.+)$")
_COURSE_RE = re.compile(
    r"\b(\d{1,2}(?:bt|egb)|prep|i[12]|inicial\s*[12]|preparatoria)\b",
    re.IGNORECASE,
)


@dataclass
class ParsedPeriod:
    start_time: str
    end_time: str
    course_abbrev: str   # e.g. "3bt"
    subject_raw: str     # e.g. "Matemáticas"


@dataclass
class ScheduleParseResult:
    periods: list[ParsedPeriod]
    errors: list[str]  # lines that could not be parsed


def parse_schedule_text(text: str) -> ScheduleParseResult:
    periods: list[ParsedPeriod] = []
    errors: list[str] = []

    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = _TIME_RE.match(line)
        if not m:
            errors.append(line)
            continue

        start, end, rest = m.group(1), m.group(2), m.group(3).strip()

        # Normalize start/end to HH:MM
        start = _pad_time(start)
        end = _pad_time(end)

        # Extract course abbreviation
        cm = _COURSE_RE.search(rest)
        if not cm:
            errors.append(line)
            continue

        raw_course = cm.group(0).lower().strip()
        course_abbrev = _COURSE_ALIASES.get(raw_course)
        if not course_abbrev:
            errors.append(line)
            continue

        # Subject is everything except the course token
        subject_raw = _COURSE_RE.sub("", rest).strip(" ,-")
        if not subject_raw:
            errors.append(line)
            continue

        periods.append(ParsedPeriod(
            start_time=start,
            end_time=end,
            course_abbrev=course_abbrev,
            subject_raw=subject_raw,
        ))

    return ScheduleParseResult(periods=periods, errors=errors)


def _pad_time(t: str) -> str:
    """Ensure HH:MM format."""
    h, m = t.split(":")
    return f"{int(h):02d}:{m}"
