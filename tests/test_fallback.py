"""Tests for rule-based fallback extractor — pure function, no LLM."""


from schoolai.skills.utils.extract_rules import extract_fallback
from schoolai.skills.utils.schema import AttendanceExtract, HomeworkExtract


# ── Attendance — absent ───────────────────────────────────────────────────────

def test_absent_name_before_verb():
    r = extract_fallback("Juan Recalde faltó hoy")
    assert r is not None and r.intent == "attendance"
    assert isinstance(r.data, AttendanceExtract)
    assert "Juan Recalde" in r.data.names
    assert r.data.status == "absent"
    assert r.data.date == "today"


def test_absent_name_after_verb():
    r = extract_fallback("Faltó Ana García en 3BT")
    assert r is not None and r.intent == "attendance"
    assert "Ana García" in r.data.names
    assert r.data.course == "3bt"


def test_absent_no_asistio():
    r = extract_fallback("Pedro no asistió ayer")
    assert r is not None
    assert r.data.status == "absent"
    assert r.data.date == "yesterday"


def test_absent_multiple_names():
    r = extract_fallback("Juan Recalde y Carlos Pérez faltaron hoy")
    assert r is not None and r.intent == "attendance"
    assert len(r.data.names) == 2


def test_absent_with_course():
    r = extract_fallback("María López faltó, 2BT")
    assert r is not None
    assert r.data.course == "2bt"
    assert r.data.complete is True


def test_absent_without_course():
    r = extract_fallback("Recalde faltó hoy")
    assert r is not None
    assert r.data.course is None
    assert r.data.complete is False


# ── Attendance — late ─────────────────────────────────────────────────────────

def test_late_status():
    r = extract_fallback("Gómez llegó tarde")
    assert r is not None and r.intent == "attendance"
    assert r.data.status == "late"
    assert "Gómez" in r.data.names


def test_late_atrasado():
    r = extract_fallback("Carlos Pérez atrasado hoy 1BT")
    assert r is not None
    assert r.data.status == "late"
    assert r.data.course == "1bt"


# ── Attendance — justified ────────────────────────────────────────────────────

def test_justified_status():
    r = extract_fallback("Ana Torres justificada hoy 10EGB")
    assert r is not None and r.intent == "attendance"
    assert r.data.status == "justified"
    assert r.data.course == "10egb"


def test_justified_con_permiso():
    r = extract_fallback("David Mora con permiso médico")
    assert r is not None
    assert r.data.status == "justified"


# ── Attendance — course verbal ────────────────────────────────────────────────

def test_absent_verbal_course():
    r = extract_fallback("López faltó, décimo egb")
    # normalize strips accents → "decimo egb" matches _COURSE_VERBAL
    assert r is not None and r.intent == "attendance"
    assert r.data.course == "10egb"


def test_absent_primero_bt():
    r = extract_fallback("Recalde faltó, primero BT")
    assert r is not None
    assert r.data.course == "1bt"


# ── Homework ──────────────────────────────────────────────────────────────────

def test_homework_basic():
    r = extract_fallback("Tarea para 3BT: página 45 ejercicios 1 al 5")
    assert r is not None and r.intent == "homework"
    assert isinstance(r.data, HomeworkExtract)
    assert r.data.course == "3bt"


def test_homework_without_course():
    r = extract_fallback("Tarea: leer páginas 10 a 15")
    assert r is not None and r.intent == "homework"
    assert r.data.course is None
    assert r.data.complete is False


def test_homework_evaluacion():
    r = extract_fallback("Evaluación el viernes, 2BT")
    assert r is not None and r.intent == "homework"
    assert r.data.course == "2bt"


def test_homework_description_preserved():
    text = "Tarea para mañana, traer materiales para 9EGB"
    r = extract_fallback(text)
    assert r is not None and r.intent == "homework"
    assert r.data.description == text.strip()


# ── Not found / ambiguous ─────────────────────────────────────────────────────

def test_empty_string_returns_none():
    assert extract_fallback("") is None


def test_greeting_returns_none():
    assert extract_fallback("Hola, buenos días") is None


def test_unrelated_text_returns_none():
    assert extract_fallback("¿Cuándo es el próximo feriado?") is None


def test_name_only_returns_none():
    """Name alone without a status keyword → uncertain → None."""
    assert extract_fallback("Juan Recalde") is None
