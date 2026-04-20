"""Genera reporte PDF de tareas pendientes para un curso."""

from __future__ import annotations

import io
from datetime import date

from fpdf import FPDF

from schoolai.skills.query.resolver import HomeworkData

_COL = {"num": 12, "subject": 40, "description": 90, "due": 28}


def generate_homework_pdf(data: HomeworkData, title: str | None = None) -> bytes:
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ── Header ──────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 14)
    heading = title or f"Tareas Pendientes — {data.grade_name}"
    pdf.cell(0, 10, _safe(heading), ln=True, align="C")

    pdf.set_font("Helvetica", "", 10)
    period = f"{data.period_start.strftime('%d/%m/%Y')} – {data.period_end.strftime('%d/%m/%Y')}"
    pdf.cell(0, 6, _safe(f"Período: {period}"), ln=True, align="C")
    pdf.ln(4)

    open_records = [r for r in data.records if r.is_open]
    if not open_records:
        pdf.set_font("Helvetica", "I", 11)
        pdf.cell(0, 8, "Sin tareas pendientes.", ln=True)
        return _to_bytes(pdf)

    # ── Table header ──────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(_COL["num"], 8, "#", border=1, fill=True)
    pdf.cell(_COL["subject"], 8, "Materia", border=1, fill=True)
    pdf.cell(_COL["description"], 8, "Descripcion", border=1, fill=True)
    pdf.cell(_COL["due"], 8, "Entrega", border=1, fill=True, ln=True)

    # ── Rows ──────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 9)
    fill = False
    for rec in sorted(open_records, key=lambda r: (r.delivery_date or date.max, r.sequence_num)):
        pdf.set_fill_color(245, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)

        due_str = rec.delivery_date.strftime("%d/%m/%Y") if rec.delivery_date else "-"
        subject_str = _safe(rec.subject or "-")
        desc_str = _safe(rec.description[:80] + ("…" if len(rec.description) > 80 else ""))

        row_h = 7
        pdf.cell(_COL["num"], row_h, str(rec.sequence_num or ""), border=1, fill=True)
        pdf.cell(_COL["subject"], row_h, subject_str, border=1, fill=True)
        pdf.cell(_COL["description"], row_h, desc_str, border=1, fill=True)
        pdf.cell(_COL["due"], row_h, due_str, border=1, fill=True, ln=True)
        fill = not fill

    # ── Footer ────────────────────────────────────────────────────────────────
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, _safe(f"Total tareas abiertas: {len(open_records)}"), ln=True)
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
