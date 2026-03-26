"""Extractor de intención para cuotas/actividades — regex, sin LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

# ── Patrones ──────────────────────────────────────────────────────────────────

_CREATE_RE = re.compile(
    r"\b(nueva?\s+actividad|crear?\s+(?:una?\s+)?actividad|agregar\s+actividad"
    r"|nueva\s+cuota|crear?\s+(?:una?\s+)?cuota)\b",
    re.IGNORECASE,
)
_PAGO_RE = re.compile(
    r"\b(pag[oó]|pagaron|pagó|abono|cancelo|canceló|entregó?\s+dinero|depositó?)\b",
    re.IGNORECASE,
)
_QUERY_RE = re.compile(
    r"\b(ver\s+cuotas?|estado\s+cuotas?|cuotas?\s+de|reporte\s+cuotas?|"
    r"ver\s+pagos?|estado\s+pagos?|quién\s+(no\s+)?pag[oó]|"
    r"quien\s+(no\s+)?pago|falta\s+pagar|pendiente[s]?\s+cuotas?)\b",
    re.IGNORECASE,
)
_EXPORT_RE = re.compile(
    r"\b(exportar|export|descargar|generar\s+reporte|excel)\b",
    re.IGNORECASE,
)
_LIST_RE = re.compile(
    r"\b(listado\s+(?:de\s+)?actividades?|listar\s+actividades?|ver\s+actividades?"
    r"|actividades?\s+activas?|qué\s+actividades?|que\s+actividades?)\b",
    re.IGNORECASE,
)
_ADD_STUDENTS_RE = re.compile(
    r"\b(agregar\s+estudiantes?|añadir\s+estudiantes?|inscribir|inscrip)",
    re.IGNORECASE,
)
_EDIT_RE = re.compile(
    r"\b(editar|modificar|cambiar|actualizar)\s+(?:actividad\s+|cuota\s+)?",
    re.IGNORECASE,
)

# Monto: "$50", "50 dólares", "50$", "50 USD"
_MONTO_RE = re.compile(
    r"\$\s*(\d+(?:[.,]\d{1,2})?)|(\d+(?:[.,]\d{1,2})?)\s*(?:dólares?|dolares?|usd|\$)",
    re.IGNORECASE,
)

# Nombre de actividad: entre comillas, tras "actividad/cuota", o tras "para el/la"
_NOMBRE_QUOTED_RE = re.compile(r'["\']([^"\']{3,80})["\']')
_NOMBRE_AFTER_RE = re.compile(
    r"\b(?:actividad|cuota)\s+(?:de\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñ\s]{3,60}?)(?=\s*\$|\s*\d|\s*para|\s*de\s+\d|$)",
    re.IGNORECASE,
)
# "para el Paseo", "para la Olimpiada"
_NOMBRE_PARA_RE = re.compile(
    r"\bpara\s+(?:el\s+|la\s+|los\s+|las\s+)?([A-ZÁÉÍÓÚÑ][a-záéíóúñ\s]{2,60}?)(?=\s*$|\s*,|\s*\d|\s*\$)",
    re.IGNORECASE,
)
# "ver cuotas Paseo", "estado Paseo de Grado" — el nombre sigue al keyword+space
# Nota: evita capturar palabras genéricas como "cuotas"/"actividades"
_NOMBRE_QUERY_RE = re.compile(
    r"\b(?:cuotas?|estado|exportar|reporte|descargar)\s+"
    r"(?:cuotas?\s+|actividades?\s+|de\s+)?"
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñA-ZÁÉÍÓÚÑ\s]{2,60}?)(?=\s*$|\s*de\s+\d)",
    re.IGNORECASE,
)

# Palabras genéricas que NO son nombres de actividades
_GENERIC_WORDS = frozenset(
    ["cuotas", "cuota", "actividades", "actividad", "pagos", "pago", "reporte"],
)


# ── Dataclass ─────────────────────────────────────────────────────────────────


@dataclass
class CuotaExtract:
    action: Literal["create", "pago", "query", "export", "list", "add_students", "edit"]
    nombre: str | None = None  # nombre de la actividad
    monto: float | None = None  # monto total o del pago
    nombres: list[str] = field(default_factory=list)  # estudiantes que pagaron
    course: str | None = None  # abreviatura de curso
    complete: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_monto(text: str) -> float | None:
    m = _MONTO_RE.search(text)
    if not m:
        return None
    raw = (m.group(1) or m.group(2)).replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_nombre(text: str) -> str | None:
    m = _NOMBRE_QUOTED_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _NOMBRE_AFTER_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _NOMBRE_PARA_RE.search(text)
    if m:
        return m.group(1).strip()
    m = _NOMBRE_QUERY_RE.search(text)
    if m:
        candidate = m.group(1).strip()
        if candidate.lower() not in _GENERIC_WORDS:
            return candidate
    return None


def _extract_course(text: str) -> str | None:
    from schoolai.skills.utils.extract_rules import _extract_course

    return _extract_course(text)


def _extract_student_names(text: str) -> list[str]:
    """Extrae nombres antes del verbo de pago."""
    m = _PAGO_RE.search(text)
    if not m:
        return []
    left = text[: m.start()].strip().rstrip(",.")
    # Separar por coma / "y"
    parts = re.split(r",\s*|\s+y\s+", left, flags=re.IGNORECASE)
    names = [p.strip() for p in parts if 3 <= len(p.strip()) <= 60]
    # Filtrar abreviaturas de curso
    from schoolai.skills.utils.extract_rules import _COURSE_RE

    return [n for n in names if not _COURSE_RE.fullmatch(n)]


# ── Public API ────────────────────────────────────────────────────────────────


def extract_cuota(text: str) -> CuotaExtract | None:
    """Detecta si el texto es una instrucción de cuota y extrae los datos.

    Retorna None si el texto no pertenece a este skill.
    """
    t = text.strip()
    if not t:
        return None

    if _EDIT_RE.search(t):
        # Remove the edit verb before extracting nombre
        cleaned = _EDIT_RE.sub("", t).strip()
        nombre = _extract_nombre(cleaned) or _extract_nombre(t)
        return CuotaExtract(action="edit", nombre=nombre, complete=bool(nombre))

    if _LIST_RE.search(t):
        return CuotaExtract(action="list", complete=True)

    if _EXPORT_RE.search(t):
        return CuotaExtract(
            action="export",
            nombre=_extract_nombre(t),
            complete=False,
        )

    if _ADD_STUDENTS_RE.search(t):
        nombre = _extract_nombre(t)
        course = _extract_course(t)
        return CuotaExtract(
            action="add_students",
            nombre=nombre,
            course=course,
            complete=bool(nombre and course),
        )

    if _CREATE_RE.search(t):
        nombre = _extract_nombre(t)
        monto = _extract_monto(t)
        course = _extract_course(t)
        return CuotaExtract(
            action="create",
            nombre=nombre,
            monto=monto,
            course=course,
            complete=bool(nombre and monto),
        )

    if _QUERY_RE.search(t):
        nombre = _extract_nombre(t)
        course = _extract_course(t)
        return CuotaExtract(
            action="query",
            nombre=nombre,
            course=course,
            complete=bool(nombre or course),
        )

    if _PAGO_RE.search(t):
        nombres = _extract_student_names(t)
        monto = _extract_monto(t)
        nombre = _extract_nombre(t)
        course = _extract_course(t)
        return CuotaExtract(
            action="pago",
            nombres=nombres,
            monto=monto,
            nombre=nombre,
            course=course,
            complete=bool(nombres and monto),
        )

    # "cuota Paseo $50" — bare form without "nueva/crear"
    if re.match(r"^\s*cuotas?\s+", t, re.IGNORECASE):
        monto = _extract_monto(t)
        if monto:
            nombre = _extract_nombre(t)
            course = _extract_course(t)
            return CuotaExtract(
                action="create",
                nombre=nombre,
                monto=monto,
                course=course,
                complete=bool(nombre and monto),
            )

    return None
