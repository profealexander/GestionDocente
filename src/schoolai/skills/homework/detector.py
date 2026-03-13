import re
from datetime import date, timedelta

HOMEWORK_KEYWORDS = [
    "tarea", "actividad", "ejercicio", "trabajo", "investigar",
    "leer", "resolver", "estudiar", "entregar", "proyecto",
    "práctica", "practica", "homework", "asignación", "asignacion",
    "examen", "prueba", "evaluación", "evaluacion",
]

COURSE_PATTERNS = [
    r"\b(inicial\s+[12]|preparatoria)\b",
    r"\b(segundo|tercero|cuarto|quinto|sexto|séptimo|septimo|octavo|noveno|décimo|decimo)\s+egb\b",
    r"\b(primero|1ero|1ro|1er|1°|1o|primer)\s*(bt|bachillerato|bachi)\b",
    r"\b(segundo|2do|2°|2o)\s*(bt|bachillerato|bachi)\b",
    r"\b(tercero|3ero|3ro|3°|3o)\s*(bt|bachillerato|bachi)\b",
    r"\b[123][°o]?\s*(bt|bachi|bachillerato|egb)\b",
]

SUBJECT_PATTERNS = [
    r"\b(matemáticas|matematicas|física|fisica|química|quimica|biología|biologia|"
    r"historia|literatura|inglés|ingles|español|computación|computacion|"
    r"contabilidad|electricidad|electrónica|electronica|geografía|geografia|"
    r"arte|música|musica|religión|religion|filosofía|filosofia|economía|economia)\b",
]

DATE_PATTERNS = [
    (r"\b(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\b", "weekday"),
    (r"\b(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?\b", "numeric"),
    (r"\b(mañana)\b", "relative"),
    (r"\b(pasado mañana|pasado manana)\b", "relative2"),
    (r"\bel\s+(\d{1,2})\b", "day_only"),
]

WEEKDAY_MAP = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}


def is_homework_message(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in HOMEWORK_KEYWORDS)


def extract_course(text: str) -> str | None:
    text_lower = text.lower()
    for pattern in COURSE_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(0).strip()
    return None


def extract_subject(text: str) -> str | None:
    text_lower = text.lower()
    for pattern in SUBJECT_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(0).strip()
    return None


def extract_date(text: str) -> date | None:
    text_lower = text.lower()
    today = date.today()

    for pattern, kind in DATE_PATTERNS:
        match = re.search(pattern, text_lower)
        if not match:
            continue

        if kind == "relative":
            return today + timedelta(days=1)

        if kind == "relative2":
            return today + timedelta(days=2)

        if kind == "weekday":
            target_wd = WEEKDAY_MAP[match.group(1)]
            days_ahead = (target_wd - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

        if kind == "numeric":
            day = int(match.group(1))
            month = int(match.group(2))
            year_raw = match.group(3)
            year = int(year_raw) if year_raw else today.year
            if year < 100:
                year += 2000
            try:
                return date(year, month, day)
            except ValueError:
                return None

        if kind == "day_only":
            day = int(match.group(1))
            month = today.month
            year = today.year
            try:
                candidate = date(year, month, day)
                if candidate < today:
                    month += 1
                    if month > 12:
                        month = 1
                        year += 1
                return date(year, month, day)
            except ValueError:
                return None

    return None
