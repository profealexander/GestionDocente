"""Tests for attendance matcher — _match_one (pure, no DB needed)."""

import pytest

from schoolai.skills.attendance.matcher import _match_one, _StudentEntry
from schoolai.skills.utils.text import normalize as _norm


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build(students: list[dict]):
    """Build matcher lookup dicts from simple student dicts.

    Each dict: id, first_name, last_name, middle_name?, second_last_name?
    """
    by_id: dict = {}
    by_first: dict = {}
    by_last: dict = {}
    by_full: dict = {}

    for s in students:
        sid = s["id"]
        first = s["first_name"]
        last = s["last_name"]
        middle = s.get("middle_name")
        second_last = s.get("second_last_name")

        short = f"{first} {last}"
        full_long = f"{first} {last} {second_last}" if second_last else short
        display = " ".join(p for p in [first, middle, last, second_last] if p)

        by_id[sid] = _StudentEntry(student=None, display=display, short=short, norm_short=_norm(short))
        by_full[_norm(short)] = sid
        by_full[_norm(full_long)] = sid
        by_full[_norm(f"{last} {first}")] = sid
        if middle:
            by_full[_norm(f"{last} {first} {middle}")] = sid
        if second_last:
            by_full[_norm(f"{last} {second_last} {first}")] = sid

        by_first.setdefault(_norm(first), []).append(sid)
        if middle:
            by_first.setdefault(_norm(middle), []).append(sid)

        by_last.setdefault(_norm(last), []).append(sid)
        if second_last:
            by_last.setdefault(_norm(second_last), []).append(sid)

    return by_id, by_first, by_last, by_full


STUDENTS = [
    {"id": 1, "first_name": "Juan",  "last_name": "Recalde"},
    {"id": 2, "first_name": "María", "last_name": "López",   "second_last_name": "Torres"},
    {"id": 3, "first_name": "Carlos","last_name": "Pérez"},
    {"id": 4, "first_name": "Juan",  "last_name": "Gómez"},   # second Juan
    {"id": 5, "first_name": "David", "last_name": "Mora",    "middle_name": "Andrés"},
]


@pytest.fixture
def lookup():
    return _build(STUDENTS)


# ── Exact match ───────────────────────────────────────────────────────────────

def test_exact_full_name(lookup):
    r = _match_one("Juan Recalde", "F", *lookup)
    assert r.resolved
    assert r.matched_id == 1


def test_exact_full_name_with_second_last(lookup):
    r = _match_one("María López Torres", "F", *lookup)
    assert r.resolved
    assert r.matched_id == 2


def test_inverted_order_last_first(lookup):
    """'Recalde Juan' should resolve to student 1."""
    r = _match_one("Recalde Juan", "F", *lookup)
    assert r.resolved
    assert r.matched_id == 1


def test_inverted_full_name_with_second_last(lookup):
    r = _match_one("López Torres María", "AT", *lookup)
    assert r.resolved
    assert r.matched_id == 2


# ── Single token ──────────────────────────────────────────────────────────────

def test_unique_last_name(lookup):
    r = _match_one("Recalde", "F", *lookup)
    assert r.resolved
    assert r.matched_id == 1


def test_unique_first_name(lookup):
    r = _match_one("Carlos", "J", *lookup)
    assert r.resolved
    assert r.matched_id == 3


def test_ambiguous_first_name(lookup):
    """Two students named Juan — should return candidates."""
    r = _match_one("Juan", "F", *lookup)
    assert r.ambiguous
    assert len(r.candidates) == 2
    ids = {c["id"] for c in r.candidates}
    assert ids == {1, 4}


# ── Fuzzy match ───────────────────────────────────────────────────────────────

def test_fuzzy_typo_first_and_last(lookup):
    """'Jhuan Recalde' (first name typo, no exact match) triggers fuzzy → resolves to id=1."""
    r = _match_one("Jhuan Recalde", "F", *lookup)
    assert r.resolved
    assert r.matched_id == 1


def test_fuzzy_typo_first_last(lookup):
    """'Juen Recalde' should fuzzy-match."""
    r = _match_one("Juen Recalde", "F", *lookup)
    assert r.resolved
    assert r.matched_id == 1


def test_fuzzy_accent_insensitive(lookup):
    """'Maria Lopez' without accents should match María López."""
    r = _match_one("Maria Lopez", "F", *lookup)
    assert r.resolved
    assert r.matched_id == 2


# ── Not found ─────────────────────────────────────────────────────────────────

def test_not_found(lookup):
    r = _match_one("Zambrano Fierro", "F", *lookup)
    assert r.not_found
    assert not r.resolved


def test_empty_string(lookup):
    r = _match_one("", "F", *lookup)
    assert r.not_found


# ── Status propagation ────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["F", "AT", "J"])
def test_status_propagated(lookup, status):
    r = _match_one("Juan Recalde", status, *lookup)
    assert r.status == status
