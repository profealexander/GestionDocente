"""
Convierte NOTIFICACION V1.docx → plantilla docxtpl con variables Jinja2.
Modifica SOLO el texto de los runs que tienen {{ }}, nada más.
Una notificación = una materia (sin loop).
"""
import os
import shutil
from docx import Document

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "NOTIFICACION V1.docx"))
OUT = os.path.join(os.path.dirname(__file__), "templates", "notificacion_tarea.docx")


def build():
    shutil.copy2(SRC, OUT)
    doc = Document(OUT)
    paras = doc.paragraphs

    # ── [0] Código documento ──────────────────────────────────────────────────
    # Unificar todos los runs en uno solo (todos son bold size=152400)
    full_text = "NOT-{{ num_seq }}-{{ iniciales_num }}-{{ anio }}"
    for r in paras[0].runs:
        r.text = ""
    paras[0].runs[0].text = full_text

    # ── [2] Fecha ─────────────────────────────────────────────────────────────
    for r in paras[2].runs:
        if "student_name" in r.text:
            r.text = " {{ fecha }}"

    # ── [3] Representante ─────────────────────────────────────────────────────
    for r in paras[3].runs:
        if "student_name" in r.text:
            r.text = " {{ representante }}"

    # ── [4] Estudiante ────────────────────────────────────────────────────────
    for r in paras[4].runs:
        if "student_name" in r.text:
            r.text = "{{ estudiante }}"

    # ── [9] Cuerpo: nombre estudiante + curso ─────────────────────────────────
    bold_count = 0
    for r in paras[9].runs:
        if "student_name" in r.text and r.bold:
            if bold_count == 0:
                r.text = "{{ estudiante }}"
            else:
                r.text = "{{ curso }}"
            bold_count += 1

    # ── [10] Asignatura ───────────────────────────────────────────────────────
    for r in paras[10].runs:
        if "student_name" in r.text:
            r.text = "{{ asignatura }}"

    # ── [11] Actividad + fecha programada ─────────────────────────────────────
    # Runs: "Actividad" " 1" ":" " " "{{ student_name }} " "[Ej:...] | " "Fecha programada:" " " "{{ student_name }} " "[Fecha]"
    sn_count = 0
    for r in paras[11].runs:
        if r.text.strip() == "1":          # quitar el "1" de "Actividad 1"
            r.text = ""
        elif "[Ej:" in r.text:             # reemplazar ejemplo pero conservar " | "
            r.text = " | "
        elif "[Fecha]" in r.text:          # quitar "[Fecha]"
            r.text = ""
        elif "student_name" in r.text:
            if sn_count == 0:
                r.text = "{{ descripcion }}"
            else:
                r.text = "{{ fecha_programada }}"
            sn_count += 1

    # ── [14] Fecha límite ─────────────────────────────────────────────────────
    # Runs: "Entregar" " las actividades...hasta el día " "{{ " "fechas sumas..." "}}" ", las cuales..."
    for r in paras[14].runs:
        if r.text.strip() in ("{{", "{{ "):
            r.text = ""
        elif "}}" in r.text:
            r.text = r.text.replace("}}", "")
        elif "fechas sumas" in r.text:
            r.text = "{{ fecha_limite }}"
        elif "hasta el día" in r.text and "{{ " not in r.text:
            # este run ya tiene el texto fijo, no tocar — el {{ }} va en otro run
            pass

    # ── [18] Firma ────────────────────────────────────────────────────────────
    for r in paras[18].runs:
        r.text = ""
    paras[18].runs[0].text = "{{ firma_placeholder }}"

    # ── [19] Nombre docente ────────────────────────────────────────────────────
    for r in paras[19].runs:
        r.text = ""
    paras[19].runs[0].text = "{{ docente_nombre }}"

    # ── [20] Cargo docente ────────────────────────────────────────────────────
    for r in paras[20].runs:
        r.text = ""
    paras[20].runs[0].text = "{{ docente_cargo }}"

    doc.save(OUT)
    print(f"Plantilla guardada: {OUT}")


if __name__ == "__main__":
    build()
