"""
Registry liviano para exponer el bot de Telegram a jobs de APScheduler.
APScheduler corre fuera del event loop de PTB, pero los jobs necesitan
el bot para enviar mensajes.
"""
from __future__ import annotations

_bot = None


def register(bot) -> None:
    global _bot
    _bot = bot


def get() -> object | None:
    return _bot
