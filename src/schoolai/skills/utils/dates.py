"""Helpers de fechas usados por extracción y guardado de tareas."""

from datetime import date, timedelta

_DAY_NAMES: dict[str, int] = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
}


def parse_date(value: str) -> date:
    """Convierte "today"/"yesterday"/nombre-de-día/ISO a date.

    Nombres de día (lunes…domingo) → ocurrencia pasada más reciente.
    Si hoy es jueves y el valor es "jueves" → hoy mismo.
    Si hoy es sábado y el valor es "jueves" → hace 2 días.
    """
    today = date.today()
    if value == "today":
        return today
    if value == "yesterday":
        return today - timedelta(days=1)
    v = value.lower().strip()
    if v in _DAY_NAMES:
        target = _DAY_NAMES[v]
        days_back = (today.weekday() - target) % 7  # 0 = hoy mismo
        return today - timedelta(days=days_back)
    try:
        return date.fromisoformat(value)
    except ValueError:
        return today


def resolve_delivery(value: str | None) -> date | None:
    """Resuelve fecha de entrega: nombre de día → próximo día hábil, ISO → date."""
    if not value:
        return None
    today = date.today()
    day_map = {
        "lunes": 0,
        "martes": 1,
        "miércoles": 2,
        "miercoles": 2,
        "jueves": 3,
        "viernes": 4,
        "sábado": 5,
        "sabado": 5,
    }
    v = value.lower().strip()
    if v in day_map:
        target = day_map[v]
        days_ahead = (target - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead)
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
