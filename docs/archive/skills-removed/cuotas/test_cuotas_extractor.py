"""Tests para el extractor de cuotas — sin LLM, sin DB."""

import pytest

from schoolai.skills.cuotas.extractor import extract_cuota


# ── create ────────────────────────────────────────────────────────────────────

def test_create_quoted_nombre():
    r = extract_cuota('nueva actividad "Paseo de Grado" $50')
    assert r is not None
    assert r.action == "create"
    assert r.nombre == "Paseo de Grado"
    assert r.monto == 50.0


def test_create_nombre_sin_comillas():
    r = extract_cuota("crear actividad Olimpiada $25")
    assert r is not None
    assert r.action == "create"
    assert r.nombre == "Olimpiada"
    assert r.monto == 25.0


def test_create_con_curso():
    r = extract_cuota('nueva actividad "Paseo" $50 para 3bt')
    assert r is not None
    assert r.action == "create"
    assert r.course == "3bt"


def test_create_monto_sin_dolar():
    r = extract_cuota("nueva actividad Olimpiada 30 dólares")
    assert r is not None
    assert r.monto == 30.0


def test_create_monto_coma_decimal():
    r = extract_cuota('nueva actividad "Colada" $12,50')
    assert r is not None
    assert r.monto == 12.50


# ── pago ─────────────────────────────────────────────────────────────────────

def test_pago_nombre_actividad():
    r = extract_cuota("García pagó $30 para el Paseo")
    assert r is not None
    assert r.action == "pago"
    assert r.nombres == ["García"]
    assert r.monto == 30.0
    assert r.nombre == "Paseo"


def test_pago_multiples_estudiantes():
    r = extract_cuota("Juan y María pagaron $20")
    assert r is not None
    assert r.action == "pago"
    assert "Juan" in r.nombres
    assert "María" in r.nombres
    assert r.monto == 20.0


def test_pago_dos_apellidos():
    r = extract_cuota("Recalde, López pagaron $15")
    assert r is not None
    assert r.action == "pago"
    assert len(r.nombres) == 2
    assert r.monto == 15.0


# ── query ─────────────────────────────────────────────────────────────────────

def test_query_con_nombre():
    r = extract_cuota("ver cuotas Paseo")
    assert r is not None
    assert r.action == "query"
    assert r.nombre == "Paseo"


def test_query_sin_nombre():
    r = extract_cuota("estado cuotas")
    assert r is not None
    assert r.action == "query"
    assert r.nombre is None


def test_query_quien_no_pago():
    r = extract_cuota("quién no pagó")
    assert r is not None
    assert r.action == "query"


# ── list ─────────────────────────────────────────────────────────────────────

def test_list_actividades():
    r = extract_cuota("listar actividades")
    assert r is not None
    assert r.action == "list"


def test_ver_actividades():
    r = extract_cuota("ver actividades activas")
    assert r is not None
    assert r.action == "list"


# ── export ────────────────────────────────────────────────────────────────────

def test_export_con_nombre():
    r = extract_cuota("exportar cuotas Paseo")
    assert r is not None
    assert r.action == "export"
    assert r.nombre == "Paseo"


def test_export_sin_nombre():
    r = extract_cuota("exportar")
    assert r is not None
    assert r.action == "export"
    assert r.nombre is None


# ── None cuando no aplica ─────────────────────────────────────────────────────

def test_no_match_asistencia():
    r = extract_cuota("García faltó hoy")
    assert r is None


def test_no_match_tarea():
    r = extract_cuota("tarea de matemáticas pág 45")
    assert r is None


def test_no_match_chat():
    r = extract_cuota("buenos días")
    assert r is None
