import re
from datetime import date, timedelta

# Aliases para nombres informales / abreviaturas de materias
# clave: texto normalizado (minúsculas, sin tildes)
SUBJECT_ALIASES: dict[str, str] = {
    "gc": "Gestión Contable y Administración Financiera",
    "gcaf": "Gestión Contable y Administración Financiera",
    "gestion contable": "Gestión Contable y Administración Financiera",
    "gestion contable y administracion financiera": "Gestión Contable y Administración Financiera",
    "pcp": "Planificación y Control Presupuestario",
    "planif": "Planificación y Control Presupuestario",
    "planificacion": "Planificación y Control Presupuestario",
    "planificacion presupuestaria": "Planificación y Control Presupuestario",
    "fil": "Filosofía",
    "filo": "Filosofía",
    "filosofia": "Filosofía",
    "costos": "Contabilidad de Costos",
    "cont costos": "Contabilidad de Costos",
    "contabilidad costos": "Contabilidad de Costos",
    "ciudadania": "Educación para la Ciudadanía",
    "edu ciudadania": "Educación para la Ciudadanía",
    "educacion ciudadania": "Educación para la Ciudadanía",
}

HOMEWORK_KEYWORDS = [
    "tarea",
    "actividad",
    "ejercicio",
    "trabajo",
    "investigar",
    "leer",
    "resolver",
    "estudiar",
    "entregar",
    "proyecto",
    "práctica",
    "practica",
    "homework",
    "asignación",
    "asignacion",
    "examen",
    "prueba",
    "evaluación",
    "evaluacion",
]

COURSE_PATTERNS = [
    r"\b(inicial\s+[12]|preparatoria)\b",
    # EGB con sufijo explícito (cubre segundo y tercero que son ambiguos con BT)
    r"\b(segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|d[eé]cimo)\s+egb\b",
    # EGB con abreviatura numérica + sufijo
    r"\b(2do|3ero|4to|5to|6to|7mo|8vo|9no|10mo)\s+egb\b",
    # EGB sin sufijo: cuarto–décimo y sus números/abreviaturas (no ambiguos con BT)
    r"\b(cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|d[eé]cimo)\b(?!\s*(bt|bachi|bachillerato|egb))",
    r"\b(4to|5to|6to|7mo|8vo|9no|10mo)\b(?!\s*(bt|bachi|bachillerato|egb))",
    # Números solos 4–10 → EGB, solo cuando NO están precedidos de una palabra de tarea
    # (evita "tarea 9", "ejercicio 5", etc.). Lookbehind fijo sin \b para Python.
    r"(?<!tarea )(?<!deber )(?<!ejercicio )(?<!examen )(?<!actividad )\b([4-9]|10)\b(?!\s*(bt|bachi|bachillerato|egb|°|o\b))",
    # Bachillerato — sufijo BT incluyendo variantes de voz: "be te", "vt", "v t", "vete"
    r"\b(primero|1ero|1ro|1er|1°|1o|primer)\s*(bt|b\.?\s*t\.?|be\s*te|vt|v\s*t|vete|bachillerato|bachi)\b",
    r"\b(segundo|segunda|2do|2da|2°|2o)\s*(bt|b\.?\s*t\.?|be\s*te|vt|v\s*t|vete|bachillerato|bachi)\b",
    r"\b(tercero|tercera|3ero|3ro|3°|3o)\s*(bt|b\.?\s*t\.?|be\s*te|vt|v\s*t|vete|bachillerato|bachi)\b",
    r"\b[123][°o]?\s*(bt|b\.?\s*t\.?|be\s*te|vt|v\s*t|vete|bachi|bachillerato|egb)\b",
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
    "lunes": 0,
    "martes": 1,
    "miércoles": 2,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sábado": 5,
    "sabado": 5,
    "domingo": 6,
}

# Pre-compiled at module load — avoids recompilation on every call
_COURSE_PATTERNS_RE = [re.compile(p) for p in COURSE_PATTERNS]
_SUBJECT_PATTERNS_RE = [re.compile(p) for p in SUBJECT_PATTERNS]
_DATE_PATTERNS_RE = [(re.compile(p), kind) for p, kind in DATE_PATTERNS]


def is_homework_message(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in HOMEWORK_KEYWORDS)


def extract_course(text: str) -> str | None:
    text_lower = text.lower()
    for pat in _COURSE_PATTERNS_RE:
        match = pat.search(text_lower)
        if match:
            return match.group(0).strip()
    return None


def extract_subject(text: str) -> str | None:
    found = extract_subjects(text)
    return found[0] if found else None


def extract_subjects(text: str) -> list[str]:
    """Devuelve todas las materias mencionadas en el texto."""
    text_lower = text.lower()
    found: list[str] = []
    for pat in _SUBJECT_PATTERNS_RE:
        for match in pat.finditer(text_lower):
            s = match.group(0).strip()
            if s not in found:
                found.append(s)
    return found


# Patrón: "tarea de [materia] de/para/en [curso]"
_SUBJ_PHRASE_RE = re.compile(
    r'\b(?:tarea|deber|deberes?|actividad|evaluaci[oó]n|examen|trabajo|investigaci[oó]n)\s+de\s+'
    r'(.+?)\s+(?:de|para|en)\s+'
    r'(?:primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|d[eé]cimo|'
    r'preparatoria|inicial|\d)',
    re.IGNORECASE,
)

# Patrón: "tarea [materia]:" o "deber [materia]:"
_SUBJ_COLON_RE = re.compile(
    r'\b(?:tarea|deber|deberes?|actividad|evaluaci[oó]n|examen|trabajo)\s+([^:]+?)\s*:',
    re.IGNORECASE,
)


def _normalize_alias(s: str) -> str:
    """Quita tildes y pone en minúsculas para búsqueda en SUBJECT_ALIASES."""
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.lower().strip()


def extract_subject_phrase(text: str) -> str | None:
    """Extrae la materia de mensajes como 'tarea de X de primero BT' o 'tarea X: desc'.

    Primero verifica aliases exactos; si no hay coincidencia retorna la frase
    para que find_subject() haga fuzzy matching en DB.
    """
    phrase: str | None = None

    m = _SUBJ_PHRASE_RE.search(text)
    if m:
        phrase = m.group(1).strip()
    else:
        m2 = _SUBJ_COLON_RE.search(text)
        if m2:
            candidate = m2.group(1).strip()
            # Excluir si es el curso en sí (contiene número o "primero/segundo/...")
            if not re.search(r'\b(\d|primero|segundo|tercero)\b', candidate, re.IGNORECASE):
                phrase = candidate

    if phrase is None:
        return None

    # Verificar alias exacto primero
    normalized = _normalize_alias(phrase)
    if normalized in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[normalized]

    return phrase


def extract_date(text: str) -> date | None:
    text_lower = text.lower()
    today = date.today()

    for pat, kind in _DATE_PATTERNS_RE:
        match = pat.search(text_lower)
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
