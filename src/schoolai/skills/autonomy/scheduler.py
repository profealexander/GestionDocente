"""APScheduler singleton — AsyncIOScheduler independiente del bot framework."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

# Module-level singleton; intentionally mutable (pylint: disable=invalid-name)
_instance: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Return the process-wide AsyncIOScheduler, creating it on first call."""
    global _instance  # pylint: disable=global-statement
    if _instance is None:
        _instance = AsyncIOScheduler(timezone="UTC")
    return _instance


async def start() -> None:
    """Start the scheduler if not already running."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("[autonomy] APScheduler iniciado")


async def stop() -> None:
    """Stop the scheduler gracefully."""
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[autonomy] APScheduler detenido")


def add_interval_job(func, seconds: int, job_id: str) -> None:
    """Register an interval job. Idempotent — replaces any existing job with the same id."""
    scheduler = get_scheduler()
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        func,
        trigger=IntervalTrigger(seconds=seconds),
        id=job_id,
        misfire_grace_time=30,
    )
    logger.info(f"[autonomy] job '{job_id}' registrado — cada {seconds}s")
