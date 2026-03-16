"""Modo activo del bot — se establece una sola vez al arrancar."""

_mode: str = "libre"  # "libre" | "jornada"


def set_mode(mode: str) -> None:
    global _mode
    _mode = mode


def is_jornada() -> bool:
    return _mode == "jornada"


def get_mode() -> str:
    return _mode
