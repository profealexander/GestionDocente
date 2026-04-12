"""Utilidades compartidas por todos los tools del orchestrator."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from loguru import logger

from schoolai.config import settings
from schoolai.skills.query.detector import QueryIntent, get_current_trimester


def _strip_tags(text: str) -> str:
    """Remove HTML tags so the LLM receives clean text."""
    return re.sub(r"<[^>]+>", "", text)


def _today() -> date:
    """Return today's date in the school's timezone."""
    tz = ZoneInfo(settings.school_timezone) if settings.school_timezone else None
    return datetime.now(tz).date()


def _parse_date(value: str) -> date:
    today = _today()
    if value in ("today", "hoy"):
        return today
    if value in ("yesterday", "ayer"):
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(value)
    except ValueError:
        logger.warning(f"[tools] fecha inválida: {value!r}, usando hoy")
        return today


def _period_to_dates(period: str, qtype: str):
    """Convert a period string to a QueryIntent."""
    today = _today()
    p = period.lower().strip()

    if p in ("today", "hoy"):
        return QueryIntent(qtype, "day", today, today)
    if p in ("yesterday", "ayer"):
        d = today - timedelta(days=1)
        return QueryIntent(qtype, "day", d, d)
    if p in ("week", "semana", "esta_semana"):
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=4)
        return QueryIntent(qtype, "week", start, end)
    if p in ("month", "mes", "este_mes"):
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(day=31)
        else:
            end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
        return QueryIntent(qtype, "month", start, end)
    num, start, end = get_current_trimester()
    return QueryIntent(qtype, "trimester", start, end, trimester_num=num)
