"""Format query results for Telegram."""

from html import escape as _e

from schoolai.skills.query.resolver import AttendanceData, HomeworkData

STATUS_ICON  = {"F": "❌", "AT": "⏰", "J": "✅"}
STATUS_LABEL = {"F": "F",  "AT": "AT", "J": "J"}

MONTH_ES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

_TABLE_W = 38   # ancho de líneas en bloque <pre>


# ── Homework — curso único ─────────────────────────────────────────────────────

def format_homework(data: HomeworkData) -> str:
    """HTML — listado de tareas agrupadas por materia."""
    period = _period_label(data)
    n = len(data.records)
    lines = [
        '📋 <b>LISTADO DE TAREAS</b>',
        f'<b>{_e(data.grade_name)}</b>  ·  {period}  ·  {n} tarea(s)',
        '──────────────────────',
    ]

    if not n:
        lines += ["", "Sin tareas registradas en este período."]
        return "\n".join(lines)

    # Agrupar por materia preservando orden de aparición
    grouped: dict[str, list] = {}
    for hw in data.records:
        key = hw.subject or "Sin materia"
        grouped.setdefault(key, []).append(hw)

    for subject, tasks in grouped.items():
        lines.append("")
        lines.append(f"<b>{_e(subject)}</b>")
        for hw in tasks:
            date_str = hw.delivery_date.strftime("%d/%m/%Y") if hw.delivery_date else "Sin fecha"
            state = "🟢 Abierta" if hw.is_open else "🔴 Cerrada"
            seq = f"#{hw.sequence_num}" if hw.sequence_num else ""
            lines.append(f"  <b>{seq}</b>  {_e(hw.description)}")
            teacher_str = f"  · 👤 {_e(hw.teacher_name)}" if hw.teacher_name else ""
            lines.append(f"  📅 {date_str}  ·  {state}{teacher_str}")

    return "\n".join(lines)


# ── Homework — multi-curso ─────────────────────────────────────────────────────

def format_homework_multi(data_list: list[HomeworkData], group_label: str = "Grupo") -> str:
    """HTML — listado de tareas agrupadas por curso y materia."""
    if not data_list:
        return "Sin tareas registradas."

    first = data_list[0]
    total = sum(len(d.records) for d in data_list)
    period = _period_label(first)
    lines = [
        '📋 <b>LISTADO DE TAREAS</b>',
        f'<b>{_e(group_label)}</b>  ·  {period}  ·  {total} tarea(s)',
        '──────────────────────',
    ]

    for data in data_list:
        n = len(data.records)
        lines.append("")
        lines.append(f"<b>▸ {_e(data.grade_name)}</b>")

        if not n:
            lines.append("   Sin tareas")
            continue

        grouped: dict[str, list] = {}
        for hw in data.records:
            key = hw.subject or "Sin materia"
            grouped.setdefault(key, []).append(hw)

        for subject, tasks in grouped.items():
            lines.append(f"  <i>{_e(subject)}</i>")
            for hw in tasks:
                date_str = hw.delivery_date.strftime("%d/%m/%Y") if hw.delivery_date else "Sin fecha"
                state = "🟢" if hw.is_open else "🔴"
                seq = f"#{hw.sequence_num}" if hw.sequence_num else ""
                lines.append(f"    <b>{seq}</b>  {_e(hw.description)}")
                teacher_str = f"  👤 {_e(hw.teacher_name)}" if hw.teacher_name else ""
                lines.append(f"    📅 {date_str}  {state}{teacher_str}")

    return "\n".join(lines)


# ── Attendance ─────────────────────────────────────────────────────────────────

def format_attendance(data: AttendanceData) -> str:
    header = _attendance_header(data)
    lines  = [header, ""]

    proceed = data.total_students - len(data.records)

    if not data.records:
        lines.append("✅ Sin novedades — todos presentes")
    else:
        for rec in data.records:
            if data.period_type == "day":
                statuses = " | ".join(
                    f"{STATUS_ICON[s]} {STATUS_LABEL[s]}" for _, s in rec.entries
                )
                lines.append(f"{rec.student_name} — {statuses}")
            else:
                f_days  = [d.day for d, s in rec.entries if s == "F"]
                at_days = [d.day for d, s in rec.entries if s == "AT"]
                j_days  = [d.day for d, s in rec.entries if s == "J"]
                parts = []
                if f_days:
                    parts.append(f"❌ F: {', '.join(map(str, f_days))}")
                if at_days:
                    parts.append(f"⏰ AT: {', '.join(map(str, at_days))}")
                if j_days:
                    parts.append(f"✅ J: {', '.join(map(str, j_days))}")
                lines.append(f"{rec.student_name} → {' | '.join(parts)}")

    lines.append("")
    lines.append(f"Procede: {proceed} estudiantes")
    return "\n".join(lines)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _period_label(data: HomeworkData) -> str:
    if data.trimester_num:
        return f"Trimestre {data.trimester_num}"
    start, end = data.period_start, data.period_end
    if start == end:
        return start.strftime("%d/%m/%Y")
    if start.year != end.year or start.month != end.month:
        if start.month == 1 and end.month == 12:
            return f"Año lectivo {start.year}"
        return f"{start.strftime('%d/%m/%y')} – {end.strftime('%d/%m/%y')}"
    return f"{MONTH_ES[start.month]} {start.year}"


def _section_header(grade_name: str, count: int) -> str:
    label  = f"── {grade_name} ─ {count} tarea{'s' if count != 1 else ''} "
    pad    = max(0, _TABLE_W - len(label))
    return label + "─" * pad


def _attendance_header(data: AttendanceData) -> str:
    if data.period_type == "day":
        period = data.period_start.strftime("%d/%m/%Y")
    elif data.period_type == "week":
        period = f"Semana {data.period_start.strftime('%d/%m')}–{data.period_end.strftime('%d/%m/%Y')}"
    elif data.period_type == "month":
        period = f"{MONTH_ES[data.period_start.month]} {data.period_start.year}"
    else:  # trimester
        period = f"Trimestre {data.period_start.strftime('%d/%m')}–{data.period_end.strftime('%d/%m/%Y')}"
    return f"📋 *{data.grade_name} — {period}*"
