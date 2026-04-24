"""
Registry liviano para exponer el bot de Telegram a jobs de APScheduler.
APScheduler corre fuera del event loop de PTB, pero los jobs necesitan
el bot para enviar mensajes — este módulo actúa como puente.
"""
from __future__ import annotations

# Module-level singleton; intentionally mutable (pylint: disable=invalid-name)
_bot_instance = None


def register(bot) -> None:
    """Store the bot reference so APScheduler jobs can access it."""
    global _bot_instance  # pylint: disable=global-statement
    _bot_instance = bot


def get() -> object | None:
    """Return the registered bot, or None if not yet set."""
    return _bot_instance
