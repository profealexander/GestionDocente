"""Genera reporte PDF de asistencia para un curso en un rango de fechas."""
from __future__ import annotations

from schoolai.skills.query.resolver import AttendanceData

from ._pdf import init_pdf, pdf_footer, safe, set_row_fill, to_bytes

_STATUS_LABEL = {"F": "Falta", "AT": "Tardanza", "J": "Justificado"}
_COL = {"student": 70, "date": 28, "status": 28}


def generate_attendance_pdf(data: AttendanceData, title: str | None = None) -> bytes:
    """Genera PDF de asistencia y retorna bytes."""
    pdf = init_pdf()

    # Header
    pdf.set_font("Helvetica", "B", 14)
    heading = title or f"Reporte de Asistencia — {data.grade_name}"
    pdf.cell(0, 10, safe(heading), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("Helvetica", "", 10)
    period = f"{data.period_start.strftime('%d/%m/%Y')} – {data.period_end.strftime('%d/%m/%Y')}"
    pdf.cell(0, 6, safe(f"Período: {period}"), new_x="LMARGIN", new_y="NEXT", align="C")  # noqa: E501
    total_label = safe(f"Total alumnos: {data.total_students}")
    pdf.cell(0, 6, total_label, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    if not data.records:
        pdf.set_font("Helvetica", "I", 11)
        msg = "Sin registros de inasistencia en el período."
        pdf.cell(0, 8, msg, new_x="LMARGIN", new_y="NEXT")
        pdf_footer(pdf)
        return to_bytes(pdf)

    # Table header
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(_COL["student"], 8, "Estudiante", border=1, fill=True)
    pdf.cell(_COL["date"], 8, "Fecha", border=1, fill=True)
    pdf.cell(_COL["status"], 8, "Estado", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    # Rows — alternating background
    pdf.set_font("Helvetica", "", 9)
    fill = False
    for rec in sorted(data.records, key=lambda r: r.student_name):
        for entry in sorted(rec.entries, key=lambda e: e.date):
            set_row_fill(pdf, fill)
            label = _STATUS_LABEL.get(entry.status, entry.status)
            pdf.cell(_COL["student"], 7, safe(rec.student_name), border=1, fill=True)
            pdf.cell(_COL["date"], 7, entry.date.strftime("%d/%m/%Y"), border=1, fill=True)
            pdf.cell(_COL["status"], 7, label, border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        fill = not fill

    # Summary
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    total = sum(len(r.entries) for r in data.records)
    pdf.cell(
        0, 7,
        safe(f"Total registros: {total}  |  Alumnos afectados: {len(data.records)}"),
        new_x="LMARGIN", new_y="NEXT",
    )

    pdf_footer(pdf)
    return to_bytes(pdf)
