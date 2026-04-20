"""
APScheduler singleton — AsyncIOScheduler.
Reemplaza el PTB job_queue para recordatorios, independiente del bot framework.
"""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def start() -> None:
    s = get_scheduler()
    if not s.running:
        s.start()
        logger.info("[autonomy] APScheduler iniciado")


async def stop() -> None:
    s = get_scheduler()
    if s.running:
        s.shutdown(wait=False)
        logger.info("[autonomy] APScheduler detenido")


def add_interval_job(func, seconds: int, job_id: str) -> None:
    """Registra un job por intervalo. Idempotente — reemplaza si ya existe."""
    s = get_scheduler()
    if s.get_job(job_id):
        s.remove_job(job_id)
    s.add_job(func, trigger=IntervalTrigger(seconds=seconds), id=job_id, misfire_grace_time=30)
    logger.info(f"[autonomy] job '{job_id}' registrado — cada {seconds}s")
