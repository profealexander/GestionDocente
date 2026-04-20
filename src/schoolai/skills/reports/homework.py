"""Genera reporte PDF de tareas pendientes para un curso."""
from __future__ import annotations

from datetime import date

from schoolai.skills.query.resolver import HomeworkData

from ._pdf import init_pdf, pdf_footer, safe, set_row_fill, to_bytes

_COL = {"num": 12, "subject": 40, "description": 90, "due": 28}


def generate_homework_pdf(data: HomeworkData, title: str | None = None) -> bytes:
    """Genera PDF de tareas y retorna bytes."""
    pdf = init_pdf()

    # Header
    pdf.set_font("Helvetica", "B", 14)
    heading = title or f"Tareas Pendientes — {data.grade_name}"
    pdf.cell(0, 10, safe(heading), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("Helvetica", "", 10)
    period = f"{data.period_start.strftime('%d/%m/%Y')} – {data.period_end.strftime('%d/%m/%Y')}"
    pdf.cell(0, 6, safe(f"Período: {period}"), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    open_records = [r for r in data.records if r.is_open]
    if not open_records:
        pdf.set_font("Helvetica", "I", 11)
        pdf.cell(0, 8, "Sin tareas pendientes.", new_x="LMARGIN", new_y="NEXT")
        pdf_footer(pdf)
        return to_bytes(pdf)

    # Table header
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(_COL["num"], 8, "#", border=1, fill=True)
    pdf.cell(_COL["subject"], 8, "Materia", border=1, fill=True)
    pdf.cell(_COL["description"], 8, "Descripcion", border=1, fill=True)
    pdf.cell(_COL["due"], 8, "Entrega", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    # Rows — alternating background
    pdf.set_font("Helvetica", "", 9)
    fill = False
    for rec in sorted(open_records, key=lambda r: (r.delivery_date or date.max, r.sequence_num)):
        set_row_fill(pdf, fill)
        due_str = rec.delivery_date.strftime("%d/%m/%Y") if rec.delivery_date else "-"
        subject_str = safe(rec.subject or "-")
        desc_str = safe(rec.description[:80] + ("…" if len(rec.description) > 80 else ""))
        pdf.cell(_COL["num"], 7, str(rec.sequence_num or ""), border=1, fill=True)
        pdf.cell(_COL["subject"], 7, subject_str, border=1, fill=True)
        pdf.cell(_COL["description"], 7, desc_str, border=1, fill=True)
        pdf.cell(_COL["due"], 7, due_str, border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        fill = not fill

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(
        0, 7, safe(f"Total tareas abiertas: {len(open_records)}"),
        new_x="LMARGIN", new_y="NEXT",
    )

    pdf_footer(pdf)
    return to_bytes(pdf)
