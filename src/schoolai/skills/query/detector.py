"""Detect query messages and extract intent, subject type and period."""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

QUERY_KEYWORDS = [
    "dame", "muestra", "mostrar", "ver", "lista", "listar",
    "quién", "quien", "quienes", "cuántos", "cuantos",
    "asistencia", "faltas", "faltaron", "tareas", "tarea",
]

ATTENDANCE_KEYWORDS = ["asistencia", "faltas", "faltaron", "atrasos", "justificados", "quien falto", "quién faltó"]
HOMEWORK_KEYWORDS   = ["tareas", "tarea", "actividades", "actividad", "pendientes"]

PERIOD_PATTERNS = [
    (r"\bhoy\b",                          "day",   0),
    (r"\besta\s+semana\b",                "week",  0),
    (r"\bsemana\s+pasada\b",              "week", -1),
    (r"\beste\s+mes\b",                   "month", 0),
    (r"\bmes\s+pasado\b",                 "month",-1),
    (r"\btrimestre\b",                    "trimester", 0),
    (r"\b(enero|february|marzo|abril|mayo|junio|julio|agosto|"
     r"septiembre|octubre|noviembre|diciembre)\b", "named_month", 0),
]

MONTH_MAP = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# Trimestres año lectivo 2025-2026
TRIMESTERS = [
    (1, date(2025, 9,  1), date(2025, 11, 30)),
    (2, date(2025, 12, 1), date(2026,  2, 28)),
    (3, date(2026, 3,  1), date(2026,  7, 31)),
]


def _norm(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclass
class QueryIntent:
    type: str           # "attendance" | "homework" | "unknown"
    period: str         # "day" | "week" | "month" | "trimester"
    period_start: date
    period_end: date
    trimester_num: int | None = None


def is_query_message(text: str) -> bool:
    t = _norm(text)
    return any(re.search(rf"\b{re.escape(kw)}\b", t) for kw in QUERY_KEYWORDS)


def get_current_trimester() -> tuple[int, date, date]:
    today = date.today()
    for num, start, end in TRIMESTERS:
        if start <= today <= end:
            return num, start, end
    # Outside school year — return last trimester
    return TRIMESTERS[-1]


def extract_intent(text: str) -> QueryIntent:
    t = _norm(text)
    today = date.today()

    # Determine query type
    qtype = "unknown"
    if any(re.search(rf"\b{re.escape(kw)}\b", t) for kw in ATTENDANCE_KEYWORDS):
        qtype = "attendance"
    elif any(re.search(rf"\b{re.escape(kw)}\b", t) for kw in HOMEWORK_KEYWORDS):
        qtype = "homework"
    elif any(kw in t for kw in ["dame", "muestra", "lista"]):
        # Ambiguous — default attendance if no clear type
        qtype = "attendance"

    # Determine period
    for pattern, period_type, offset in PERIOD_PATTERNS:
        m = re.search(pattern, t)
        if not m:
            continue

        if period_type == "day":
            d = today + timedelta(days=offset)
            return QueryIntent(qtype, "day", d, d)

        if period_type == "week":
            week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
            week_end = week_start + timedelta(days=4)
            return QueryIntent(qtype, "week", week_start, week_end)

        if period_type == "month":
            if offset == 0:
                start = today.replace(day=1)
            else:
                first = today.replace(day=1)
                start = (first - timedelta(days=1)).replace(day=1)
            end = _month_end(start)
            return QueryIntent(qtype, "month", start, end)

        if period_type == "trimester":
            num, start, end = get_current_trimester()
            return QueryIntent(qtype, "trimester", start, end, trimester_num=num)

        if period_type == "named_month":
            month_name = m.group(1) if m.lastindex else m.group(0)
            month_num = MONTH_MAP.get(_norm(month_name))
            if month_num:
                year = today.year if month_num <= today.month else today.year - 1
                start = date(year, month_num, 1)
                end = _month_end(start)
                return QueryIntent(qtype, "month", start, end)

    # Default periods
    if qtype == "homework":
        num, start, end = get_current_trimester()
        return QueryIntent(qtype, "trimester", start, end, trimester_num=num)

    # Default attendance → today
    return QueryIntent(qtype, "day", today, today)


def _month_end(start: date) -> date:
    if start.month == 12:
        return start.replace(day=31)
    return start.replace(month=start.month + 1, day=1) - timedelta(days=1)
