"""Utilidades puras del Modo Jornada — sin dependencias internas del paquete."""

from datetime import date, datetime, timedelta
from datetime import time as _time
from functools import cache

_ORDINAL = {1: "1RA", 2: "2DA", 3: "3RA", 4: "4TA", 5: "5TA", 6: "6TA", 7: "7MA", 8: "8VA"}


@cache
def _parse_time(s: str) -> _time:
    """Convierte 'HH:MM' a time. Cacheado porque los horarios no cambian."""
    h, m = s.split(":")
    return _time(int(h), int(m))


def _current_period_index(periods: list[dict]) -> int:
    """Retorna el índice del período activo o próximo según la hora actual.

    - Dentro de un período → ese índice
    - Entre períodos       → el siguiente
    - Todos pasaron        → len(periods)
    - No ha empezado aún   → 0
    """
    from zoneinfo import ZoneInfo

    from schoolai.config import settings as _s

    now = datetime.now(ZoneInfo(_s.school_timezone)).time()
    for i, p in enumerate(periods):
        start = _parse_time(p["start_time"])
        end = _parse_time(p["end_time"])
        if start <= now <= end:
            return i
        if now < start:
            return i
    return len(periods)


def _hora_label(n: int) -> str:
    return f"{_ORDINAL.get(n, f'{n}RA')} HORA"


def _build_period_list(periods) -> list[dict]:
    return [
        {
            "period_num": p.period_num,
            "start_time": p.start_time,
            "end_time":   p.end_time,
            "grade_id":   p.grade_id,
            "grade_name": p.grade.name,
            "subject_id": p.subject_id,
            "subject_name": p.subject.name,
        }
        for p in periods
    ]


def _extract_day_from_text(text: str) -> int:
    """Extrae el día de semana del texto. Retorna el día de hoy por defecto."""
    _DAY_WORDS: dict[str, int] = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4,
        "hoy": -1, "mañana": -2, "manana": -2,
    }
    t = text.lower()
    for word, val in _DAY_WORDS.items():
        if word in t:
            if val == -1:
                return date.today().weekday()
            if val == -2:
                return (date.today() + timedelta(days=1)).weekday() % 5
            return val
    return date.today().weekday()
