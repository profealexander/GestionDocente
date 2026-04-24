"""Logging centralizado para todos los procesos SchoolAI.

Uso:
    from schoolai.logging import setup_logging
    setup_logging("gateway")   # → logs/gateway_YYYY-MM-DD.log
    setup_logging("bot")       # → logs/bot_YYYY-MM-DD.log
    setup_logging("api")       # → logs/api_YYYY-MM-DD.log
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger


class _InterceptHandler(logging.Handler):
    """Redirige el logger stdlib (uvicorn, sqlalchemy, httpx…) a loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # type: ignore[assignment]

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(service: str) -> None:
    """Configura loguru para el proceso *service* y captura el logger stdlib."""
    from schoolai.config import settings

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()

    logger.add(
        sys.stderr,
        level="INFO",
        colorize=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{extra[service]}</cyan> | {message}",
    )
    logger.add(
        log_dir / f"{service}_{{time:YYYY-MM-DD}}.log",
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {message}",
    )

    # Inyecta el nombre del servicio en todos los registros
    logger.configure(extra={"service": service})

    # Captura loggers stdlib (uvicorn, sqlalchemy, httpx, telegram…)
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(name).handlers = [_InterceptHandler()]
        logging.getLogger(name).propagate = False
