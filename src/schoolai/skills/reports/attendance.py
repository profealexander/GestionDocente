"""Genera reporte PDF de asistencia para un curso en un rango de fechas."""

from __future__ import annotations

import io
from datetime import date

from fpdf import FPDF

from schoolai.skills.query.resolver import AttendanceData

_STATUS_LABEL = {"F": "Falta", "AT": "Tardanza", "J": "Justificado"}
_COL_WIDTHS = {"student": 70, "date": 28, "status": 28}


def generate_attendance_pdf(data: AttendanceData, title: str | None = None) -> bytes:
    """Genera PDF de asistencia y retorna bytes."""
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ── Header ──────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 14)
    heading = title or f"Reporte de Asistencia — {data.grade_name}"
    pdf.cell(0, 10, _safe(heading), ln=True, align="C")

    pdf.set_font("Helvetica", "", 10)
    period = f"{data.period_start.strftime('%d/%m/%Y')} – {data.period_end.strftime('%d/%m/%Y')}"
    pdf.cell(0, 6, _safe(f"Período: {period}"), ln=True, align="C")
    pdf.cell(0, 6, _safe(f"Total alumnos: {data.total_students}"), ln=True, align="C")
    pdf.ln(4)

    if not data.records:
        pdf.set_font("Helvetica", "I", 11)
        pdf.cell(0, 8, "Sin registros de inasistencia en el período.", ln=True)
        return _to_bytes(pdf)

    # ── Table header ──────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(_COL_WIDTHS["student"], 8, "Estudiante", border=1, fill=True)
    pdf.cell(_COL_WIDTHS["date"], 8, "Fecha", border=1, fill=True)
    pdf.cell(_COL_WIDTHS["status"], 8, "Estado", border=1, fill=True, ln=True)

    # ── Rows ──────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 9)
    fill = False
    for rec in sorted(data.records, key=lambda r: r.student_name):
        for entry in sorted(rec.entries, key=lambda e: e.date):
            pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
            pdf.cell(_COL_WIDTHS["student"], 7, _safe(rec.student_name), border=1, fill=True)
            pdf.cell(_COL_WIDTHS["date"], 7, entry.date.strftime("%d/%m/%Y"), border=1, fill=True)
            label = _STATUS_LABEL.get(entry.status, entry.status)
            pdf.cell(_COL_WIDTHS["status"], 7, label, border=1, fill=True, ln=True)
        fill = not fill

    # ── Summary ───────────────────────────────────────────────────────────────
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    total_entries = sum(len(r.entries) for r in data.records)
    pdf.cell(0, 7, _safe(f"Total registros: {total_entries}  |  Alumnos afectados: {len(data.records)}"), ln=True)

    # ── Footer ────────────────────────────────────────────────────────────────
    pdf.set_y(-20)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 6, _safe(f"Generado {date.today().strftime('%d/%m/%Y')} — SchoolAI"), align="C")

    return _to_bytes(pdf)


def _safe(text: str) -> str:
    replacements = {"—": "-", "–": "-", "\u2019": "'", "\u201c": '"', "\u201d": '"'}
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _to_bytes(pdf: FPDF) -> bytes:
    buf = io.BytesIO()
    buf.write(pdf.output())
    return buf.getvalue()
