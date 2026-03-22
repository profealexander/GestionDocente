"""Tests for date/delivery utility functions — no LLM, no DB."""

from datetime import date, timedelta

import pytest

from schoolai.skills.utils.dates import parse_date as _parse_date, resolve_delivery as _resolve_delivery


# ── _parse_date ───────────────────────────────────────────────────────────────

def test_parse_date_today():
    assert _parse_date("today") == date.today()


def test_parse_date_yesterday():
    assert _parse_date("yesterday") == date.today() - timedelta(days=1)


def test_parse_date_iso():
    assert _parse_date("2026-03-15") == date(2026, 3, 15)


def test_parse_date_invalid_falls_back_to_today():
    assert _parse_date("mañana") == date.today()
    assert _parse_date("") == date.today()
    assert _parse_date("32-13-2026") == date.today()


# ── _resolve_delivery ─────────────────────────────────────────────────────────

def test_resolve_delivery_none():
    assert _resolve_delivery(None) is None


def test_resolve_delivery_null_string():
    assert _resolve_delivery("null") is None


def test_resolve_delivery_iso_date():
    assert _resolve_delivery("2026-04-10") == date(2026, 4, 10)


@pytest.mark.parametrize("day_name,weekday_num", [
    ("lunes", 0), ("martes", 1), ("miércoles", 2), ("miercoles", 2),
    ("jueves", 3), ("viernes", 4),
])
def test_resolve_delivery_weekday(day_name, weekday_num):
    result = _resolve_delivery(day_name)
    assert result is not None
    assert result.weekday() == weekday_num
    assert result > date.today()  # always in the future


def test_resolve_delivery_invalid_returns_none():
    assert _resolve_delivery("pasado mañana") is None
