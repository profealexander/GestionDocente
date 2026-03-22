"""Servicio de cron persistente.

Inspirado en NanoBot (HKUDS/nanobot) cron/service.py.

Los jobs se definen en código y su hora se persiste en cron.json
(dentro de LOG_DIR). Al reiniciar el bot, todos se re-registran
con la hora guardada — no se pierde la configuración.

Uso:
    from schoolai.bot.cron_service import cron_service

    # En _post_init():
    cron_service.load()
    cron_service.register_callback("morning_notify", job_morning_notify)
    cron_service.register_with_app(app)

Comando /cron:
    /cron                         — lista jobs activos con su hora
    /cron morning_notify 07:00   — cambia la hora del job y recalendariza
"""

from __future__ import annotations

import json
from datetime import time as _time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

if TYPE_CHECKING:
    from telegram.ext import Application

# ── Definición de jobs del sistema ────────────────────────────────────────────

_SYSTEM_JOBS: dict[str, dict[str, Any]] = {
    "morning_notify": {
        "hour": 6,
        "minute": 30,
        "description": "Aviso diario de inicio de jornada a docentes",
    },
}


class CronService:
    """Gestiona jobs periódicos con configuración persistente."""

    def __init__(self) -> None:
        self._path: Path | None = None
        self._jobs: dict[str, dict[str, Any]] = {}
        self._callbacks: dict[str, Callable] = {}
        self._app: Any = None  # telegram.ext.Application

    # ── Inicialización ─────────────────────────────────────────────────────────

    def load(self, config_dir: str | Path = "logs") -> None:
        """Carga la configuración desde cron.json; usa defaults si no existe."""
        self._path = Path(config_dir) / "cron.json"

        if self._path.exists():
            try:
                stored = json.loads(self._path.read_text())
                # Merge: defaults base + valores guardados por encima
                self._jobs = {}
                for name, defaults in _SYSTEM_JOBS.items():
                    self._jobs[name] = {**defaults, **stored.get(name, {})}
                logger.info(f"[cron] config cargada desde {self._path}")
                return
            except Exception as e:
                logger.warning(f"[cron] error leyendo {self._path}: {e}")

        # Primera vez: usar defaults
        self._jobs = {name: dict(cfg) for name, cfg in _SYSTEM_JOBS.items()}
        self._save()
        logger.info(f"[cron] config inicializada con defaults en {self._path}")

    def register_callback(self, name: str, fn: Callable) -> None:
        """Asocia una función al job con ese nombre."""
        self._callbacks[name] = fn

    def register_with_app(self, app: "Application") -> None:
        """Registra todos los jobs con el job_queue de la aplicación Telegram."""
        self._app = app
        for name, fn in self._callbacks.items():
            if name in self._jobs:
                t = self._get_time(name)
                app.job_queue.run_daily(fn, time=t, name=name)
                logger.info(f"[cron] {name} → {t.strftime('%H:%M')} (diario)")

    # ── API pública ────────────────────────────────────────────────────────────

    def list_jobs(self) -> list[dict[str, str]]:
        """Devuelve info de todos los jobs registrados."""
        return [
            {
                "name": name,
                "time": self._get_time(name).strftime("%H:%M"),
                "description": cfg.get("description", ""),
            }
            for name, cfg in self._jobs.items()
            if name in self._callbacks
        ]

    def set_time(self, job_name: str, hour: int, minute: int) -> None:
        """Cambia la hora de un job, persiste y recalendariza si el bot está activo."""
        if job_name not in self._jobs:
            raise ValueError(f"Job desconocido: {job_name!r}. Disponibles: {list(self._jobs)}")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f"Hora inválida: {hour:02d}:{minute:02d}")

        self._jobs[job_name]["hour"] = hour
        self._jobs[job_name]["minute"] = minute
        self._save()
        logger.info(f"[cron] {job_name} → {hour:02d}:{minute:02d}")

        # Recalendarizar en el job_queue activo
        if self._app is not None:
            self._reschedule(job_name)

    # ── Internos ───────────────────────────────────────────────────────────────

    def _get_time(self, job_name: str) -> _time:
        cfg = self._jobs.get(job_name, {})
        return _time(cfg.get("hour", 6), cfg.get("minute", 30))

    def _save(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Solo persistir hora y minuto (no description — esa viene del código)
        minimal = {
            name: {"hour": cfg["hour"], "minute": cfg["minute"]}
            for name, cfg in self._jobs.items()
        }
        self._path.write_text(json.dumps(minimal, indent=2))

    def _reschedule(self, job_name: str) -> None:
        """Cancela el job existente y lo vuelve a registrar con la nueva hora."""
        for job in self._app.job_queue.jobs():
            if job.name == job_name:
                job.schedule_removal()

        fn = self._callbacks.get(job_name)
        if fn:
            t = self._get_time(job_name)
            self._app.job_queue.run_daily(fn, time=t, name=job_name)
            logger.info(f"[cron] {job_name} recalendarizado → {t.strftime('%H:%M')}")


# ── Singleton global ───────────────────────────────────────────────────────────
cron_service = CronService()
