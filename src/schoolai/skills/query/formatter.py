"""Format query results for Telegram (Markdown)."""

from datetime import date

from schoolai.skills.query.resolver import AttendanceData, HomeworkData

STATUS_ICON = {"F": "❌", "AT": "⏰", "J": "✅"}
STATUS_LABEL = {"F": "F", "AT": "AT", "J": "J"}

MONTH_ES = [
    "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]


def format_attendance(data: AttendanceData) -> str:
    header = _attendance_header(data)
    lines = [header, ""]

    absent_count = len(data.records)
    proceed_count = data.total_students - absent_count

    if not data.records:
        lines.append("✅ Sin novedades — todos presentes")
    else:
        for rec in data.records:
            if data.period_type == "day":
                # Single day: just show status
                statuses = " | ".join(
                    f"{STATUS_ICON[s]} {STATUS_LABEL[s]}" for _, s in rec.entries
                )
                lines.append(f"{rec.student_name} — {statuses}")
            else:
                # Week/month: group by status, show day numbers
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
    lines.append(f"Procede: {proceed_count} estudiantes")

    return "\n".join(lines)


def format_homework(data: HomeworkData) -> str:
    if data.trimester_num:
        period_label = f"Trimestre {data.trimester_num}"
    else:
        period_label = f"{data.period_start.strftime('%d/%m')} – {data.period_end.strftime('%d/%m/%Y')}"

    lines = [
        f"📚 *Tareas — {data.grade_name}*",
        f"{period_label} · {len(data.records)} tarea(s)",
        "",
    ]

    if not data.records:
        lines.append("Sin tareas registradas en este período.")
        return "\n".join(lines)

    for i, hw in enumerate(data.records, 1):
        subject = f"_{hw.subject}_" if hw.subject else "_Sin asignatura_"
        delivery = hw.delivery_date.strftime("%d/%m/%Y") if hw.delivery_date else "Sin fecha"
        status = "🟢 Abierta" if hw.is_open else "🔴 Cerrada"
        desc = hw.description[:80] + "..." if len(hw.description) > 80 else hw.description
        lines.append(f"{i}. {desc}")
        lines.append(f"   {subject} · 📅 {delivery} · {status}")

    return "\n".join(lines)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _attendance_header(data: AttendanceData) -> str:
    if data.period_type == "day":
        period = data.period_start.strftime("%d/%m/%Y")
    elif data.period_type == "week":
        period = f"Semana {data.period_start.strftime('%d/%m')}–{data.period_end.strftime('%d/%m/%Y')}"
    elif data.period_type == "month":
        period = f"{MONTH_ES[data.period_start.month]} {data.period_start.year}"
    else:
        period = f"Trimestre"

    return f"📋 *{data.grade_name} — {period}*"
