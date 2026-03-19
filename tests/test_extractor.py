"""Tests for extractor pure functions — no LLM call, no DB."""

from datetime import date, timedelta

import pytest

from schoolai.skills.utils.extract_llm import _build_result, _nullify
from schoolai.skills.utils.dates import parse_date as _parse_date, resolve_delivery as _resolve_delivery
from schoolai.skills.utils.schema import (
    AttendanceExtract,
    ChatExtract,
    HomeworkExtract,
    HomeworkReportExtract,
    QueryExtract,
)


# ── _nullify ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["null", "NULL", "Null", "none", "NONE", "n/a", "N/A", ""])
def test_nullify_null_strings(value):
    assert _nullify(value) is None


def test_nullify_none_input():
    assert _nullify(None) is None


def test_nullify_real_value():
    assert _nullify("Matemáticas") == "Matemáticas"


def test_nullify_preserves_whitespace_content():
    assert _nullify("Lengua y Literatura") == "Lengua y Literatura"


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


# ── _build_result ─────────────────────────────────────────────────────────────

def test_build_attendance():
    raw = {
        "intent": "attendance",
        "names": ["Juan Recalde"],
        "course": "3bt",
        "date": "today",
        "status": "absent",
        "complete": True,
    }
    r = _build_result(raw)
    assert r.intent == "attendance"
    assert isinstance(r.data, AttendanceExtract)
    assert r.data.names == ["Juan Recalde"]
    assert r.data.course == "3bt"
    assert r.data.status == "absent"
    assert r.data.complete is True


def test_build_attendance_null_course():
    raw = {"intent": "attendance", "names": ["Ana"], "course": "null", "date": "today", "status": "late", "complete": False}
    r = _build_result(raw)
    assert r.data.course is None
    assert r.data.complete is False


def test_build_homework():
    raw = {
        "intent": "homework",
        "description": "Página 45 ejercicios 1 al 5",
        "course": "2bt",
        "subject": "Matemáticas",
        "delivery_date": "viernes",
        "complete": True,
    }
    r = _build_result(raw)
    assert r.intent == "homework"
    assert isinstance(r.data, HomeworkExtract)
    assert r.data.description == "Página 45 ejercicios 1 al 5"
    assert r.data.subject == "Matemáticas"
    assert r.data.complete is True


def test_build_query_with_subject():
    raw = {
        "intent": "query",
        "query_type": "homework",
        "courses": ["1bt", "2bt"],
        "period": "trimester",
        "subject": "Filosofía",
        "complete": True,
    }
    r = _build_result(raw)
    assert r.intent == "query"
    assert isinstance(r.data, QueryExtract)
    assert r.data.subject == "Filosofía"
    assert r.data.courses == ["1bt", "2bt"]


def test_build_query_courses_as_string():
    """LLM sometimes returns courses as string instead of list."""
    raw = {"intent": "query", "query_type": "attendance", "courses": "3bt", "period": "today", "complete": True}
    r = _build_result(raw)
    assert isinstance(r.data.courses, list)
    assert r.data.courses == ["3bt"]


def test_build_query_null_subject():
    raw = {"intent": "query", "query_type": "homework", "courses": ["3bt"], "period": "week", "subject": "null", "complete": True}
    r = _build_result(raw)
    assert r.data.subject is None


def test_build_homework_report():
    raw = {
        "intent": "homework_report",
        "names": ["Carlos Pérez"],
        "homework_ref": 3,
        "course": "1bt",
        "subject": "Física",
        "status": "missing",
        "complete": True,
    }
    r = _build_result(raw)
    assert r.intent == "homework_report"
    assert isinstance(r.data, HomeworkReportExtract)
    assert r.data.homework_ref == 3
    assert r.data.status == "missing"


def test_build_homework_report_no_ref():
    raw = {"intent": "homework_report", "names": ["Ana"], "homework_ref": None, "course": "null", "subject": "null", "status": "missing", "complete": False}
    r = _build_result(raw)
    assert r.data.homework_ref is None
    assert r.data.complete is False


def test_build_chat():
    r = _build_result({"intent": "chat"})
    assert r.intent == "chat"
    assert isinstance(r.data, ChatExtract)


def test_build_unknown_intent_falls_back_to_chat():
    r = _build_result({"intent": "something_unexpected"})
    assert r.intent == "something_unexpected"
    assert isinstance(r.data, ChatExtract)
