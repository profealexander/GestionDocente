"""Definición de jobs para APScheduler. Llamar register_jobs(bot) en _post_init."""
from __future__ import annotations

from loguru import logger

from . import bot_registry
from .scheduler import start


async def register_jobs(bot) -> None:
    """Registra el bot y arranca APScheduler."""
    bot_registry.register(bot)
    await start()
    logger.info("[autonomy] jobs registrados")
