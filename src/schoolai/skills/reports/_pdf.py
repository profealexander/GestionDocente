"""Shared PDF helpers — used by attendance.py and homework.py."""
from __future__ import annotations

import io
from datetime import date

from fpdf import FPDF

_REPLACEMENTS = {
    "\u2014": "-", "\u2013": "-", "\u2019": "'", "\u201c": '"', "\u201d": '"',
}


def safe(text: str) -> str:
    """Replace non-latin-1 chars for fpdf2 compatibility."""
    for src, dst in _REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def init_pdf() -> FPDF:
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    return pdf


def set_row_fill(pdf: FPDF, fill: bool) -> None:
    """Set alternating row background color."""
    if fill:
        pdf.set_fill_color(245, 245, 245)
    else:
        pdf.set_fill_color(255, 255, 255)


def pdf_footer(pdf: FPDF) -> None:
    pdf.set_y(-20)
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 6, safe(f"Generado {date.today().strftime('%d/%m/%Y')} — SchoolAI"), align="C")


def to_bytes(pdf: FPDF) -> bytes:
    buf = io.BytesIO()
    buf.write(pdf.output())
    return buf.getvalue()
