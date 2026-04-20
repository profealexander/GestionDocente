"""Definición de jobs para APScheduler. Llamar register_jobs(bot) en _post_init."""
from __future__ import annotations

from loguru import logger

from schoolai.skills.reminders.dispatcher import dispatch_due_reminders

from . import bot_registry
from .scheduler import add_interval_job, start


async def _job_dispatch_reminders() -> None:
    bot = bot_registry.get()
    if bot is None:
        logger.warning("[autonomy:reminders] bot no registrado aún — skip")
        return
    await dispatch_due_reminders(bot)


async def register_jobs(bot) -> None:
    """Registra el bot y arranca APScheduler con todos los jobs autónomos."""
    bot_registry.register(bot)
    add_interval_job(_job_dispatch_reminders, seconds=300, job_id="dispatch_reminders")
    await start()
    logger.info("[autonomy] jobs registrados — reminders cada 5 min")
