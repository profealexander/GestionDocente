"""Generador de documentos Word y PDF para notificaciones."""
from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass
from datetime import date

from docxtpl import DocxTemplate
from fpdf import FPDF

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
SIGNATURES_DIR = os.path.join(os.path.dirname(__file__), "signatures")

_REPLACEMENTS = {"—": "-", "–": "-", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2026": "..."}

def _safe(text: str) -> str:
    """Reemplaza caracteres fuera de latin-1 para compatibilidad con fpdf."""
    for src, dst in _REPLACEMENTS.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


@dataclass
class NotificacionContext:
    num_doc: str
    fecha: str
    representante: str
    estudiante: str
    curso: str
    asignatura: str
    descripcion: str
    fecha_programada: str
    fecha_limite: str
    docente_nombre: str
    docente_cargo: str
    firma_path: str | None = None   # ruta a imagen de firma (solo PDF)


# ── Word ──────────────────────────────────────────────────────────────────────

def generate_word(ctx: NotificacionContext) -> bytes:
    """Genera el documento Word sin firma. Retorna bytes."""
    tpl = DocxTemplate(os.path.join(TEMPLATES_DIR, "notificacion_tarea.docx"))
    # num_doc format: NOT-2026-EA-001-CE-01
    num_parts = ctx.num_doc.split("-")
    anio      = num_parts[1] if len(num_parts) > 1 else ""
    num_seq   = num_parts[3] if len(num_parts) > 3 else (num_parts[2] if len(num_parts) > 2 else "001")
    ini_num   = num_parts[4] if len(num_parts) > 4 else (num_parts[3] if len(num_parts) > 3 else "")
    context = {
        "num_seq":           num_seq,
        "iniciales_num":     ini_num,
        "anio":              anio,
        "fecha":             ctx.fecha,
        "representante":     ctx.representante,
        "estudiante":        ctx.estudiante,
        "curso":             ctx.curso,
        "asignatura":        ctx.asignatura,
        "descripcion":       ctx.descripcion,
        "fecha_programada":  ctx.fecha_programada,
        "fecha_limite":      ctx.fecha_limite,
        "docente_nombre":    ctx.docente_nombre,
        "docente_cargo":     ctx.docente_cargo,
        "firma_placeholder": "",  # en blanco para Word
    }
    tpl.render(context)
    buf = io.BytesIO()
    tpl.save(buf)
    return buf.getvalue()


# ── PDF ───────────────────────────────────────────────────────────────────────

MONTHS_ES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha_larga(d: date) -> str:
    return f"{d.day} de {MONTHS_ES[d.month]} de {d.year}"


class _NotifPDF(FPDF):
    def __init__(self, docente_nombre: str, docente_cargo: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self._doc_nombre = docente_nombre
        self._doc_cargo  = docente_cargo
        self.set_margins(left=25, top=25, right=20)
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        # Línea superior decorativa
        self.set_draw_color(0, 70, 127)
        self.set_line_width(1)
        self.line(30, 15, 185, 15)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, _safe(f"{self._doc_nombre} - {self._doc_cargo}"), align="C")
        self.set_draw_color(0, 70, 127)
        self.set_line_width(0.5)
        self.line(30, self.get_y() - 2, 185, self.get_y() - 2)


def generate_pdf(ctx: NotificacionContext) -> bytes:
    """Genera el PDF con firma si está disponible. Retorna bytes."""
    pdf = _NotifPDF(ctx.docente_nombre, ctx.docente_cargo)
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)

    def ln(h=4):
        pdf.ln(h)

    W = 165  # ancho útil: 210 - 25 - 20

    def text(txt, size=11, bold=False, italic=False, align="L", color=(0, 0, 0)):
        style = ""
        if bold:   style += "B"
        if italic: style += "I"
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*color)
        pdf.set_x(25)
        pdf.multi_cell(W, 6, _safe(txt), align=align)

    # Código documento (derecha)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, ctx.num_doc, align="R")
    ln(3)

    # Título
    text("NOTIFICACIÓN POR NO ENTREGA DE ACTIVIDADES",
         size=13, bold=True, align="C", color=(0, 70, 127))
    ln(6)

    # Datos
    text(f"Fecha: {ctx.fecha}")
    text(f"Representante Legal: {ctx.representante}")
    text(f"Estudiante: {ctx.estudiante}")
    text("Asunto: Notificación de falta de entrega de TAREAS DE APRENDIZAJE.", bold=True)
    ln(4)

    text("De mi consideración:", bold=True)
    ln(3)

    text(
        f"Por medio de la presente, informo a usted que su representado/a, el estudiante "
        f"{ctx.estudiante}, de {ctx.curso}, no ha cumplido con la entrega de la(s) "
        f"siguiente(s) actividad(es) formativa(s):"
    )
    ln(3)

    # Tarea
    pdf.set_font("Helvetica", "", 10)
    pdf.set_fill_color(240, 245, 255)
    pdf.set_text_color(0, 0, 0)
    pdf.set_x(25)
    pdf.multi_cell(W, 6, _safe(f"  Asignatura: {ctx.asignatura}"), fill=True)
    ln(1)
    pdf.set_x(25)
    pdf.multi_cell(W, 6, _safe(f"  Actividad: {ctx.descripcion}  |  Fecha: {ctx.fecha_programada}"), fill=True)
    ln(3)

    text(
        "Esta situación afecta directamente el proceso de evaluación formativa y el "
        "desarrollo de sus destrezas. Con el fin de evitar que el estudiante caiga en "
        "un promedio inferior a 7,00/10, se le solicita:"
    )
    ln(2)
    text("  • Justificar la inasistencia o falta de entrega en un plazo de 48 horas.")
    text(
        f"  • Entregar las actividades pendientes hasta el día {ctx.fecha_limite}, las cuales "
        f"serán calificadas según lo establece el Modelo Institucional de Evaluación para "
        f"casos de entrega tardía."
    )
    ln(3)

    text(
        "Le recordamos que, según el Art. 13 de la LOEI, es obligación de los padres de "
        "familia participar en el proceso educativo y supervisar el cumplimiento de las "
        "tareas escolares."
    )
    ln(8)

    text("Atentamente,")
    ln(2)

    # Firma
    if ctx.firma_path and os.path.exists(ctx.firma_path):
        try:
            pdf.image(ctx.firma_path, x=pdf.get_x(), y=pdf.get_y(), h=20)
            ln(22)
        except Exception:
            ln(20)
    else:
        ln(20)

    # Línea de firma
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.3)
    x = pdf.get_x()
    y = pdf.get_y()
    pdf.line(x, y, x + 60, y)
    ln(3)

    text(ctx.docente_nombre, bold=True)
    text(ctx.docente_cargo)

    return bytes(pdf.output())


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_signature_path(teacher_id: int) -> str | None:
    for ext in ("png", "jpg", "jpeg"):
        p = os.path.join(SIGNATURES_DIR, f"{teacher_id}.{ext}")
        if os.path.exists(p):
            return p
    return None
