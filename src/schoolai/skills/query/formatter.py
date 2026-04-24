"""Format query results for Telegram."""

from html import escape as _e

from schoolai.skills.query.resolver import AttendanceData, HomeworkData

STATUS_ICON = {"F": "❌", "AT": "⏰", "J": "✅"}
STATUS_LABEL = {"F": "F", "AT": "AT", "J": "J"}



_HORA_SUFFIX = {1: "ra", 2: "da", 3: "ra", 4: "ta", 5: "ta", 6: "ta", 7: "ma", 8: "va", 9: "na", 10: "ma"}


def _hora_label(n: int) -> str:
    return f"{n}{_HORA_SUFFIX.get(n, 'ta')}"


def _format_day_consolidated(records) -> list[str]:
    """Day view grouped by period/subject with individual status icons per student."""
    # Build period_start → number map from stored period_number values
    start_to_num: dict[str, int] = {}
    for rec in records:
        for e in rec.entries:
            if e.period_start and e.period_number is not None:
                start_to_num[e.period_start] = e.period_number

    # Fallback: rank by sorted start times in the data
    if not start_to_num:
        all_starts = sorted({e.period_start for rec in records for e in rec.entries if e.period_start})
        start_to_num = {s: idx + 1 for idx, s in enumerate(all_starts)}

    # Group by (sort_key, period_number, subject_name)
    groups: dict[tuple, list[tuple[str, str]]] = {}
    for rec in records:
        for e in rec.entries:
            num = start_to_num.get(e.period_start or "")
            key = (e.period_start or "", num or 0, e.subject_name or "—")
            groups.setdefault(key, []).append((rec.student_name, e.status))

    lines: list[str] = []
    for (period_start, num, subject_name), students in sorted(groups.items()):
        hora = f"{_hora_label(num)} hora" if num else (period_start or "")
        statuses = [s for _, s in students]
        if all(s == "F" for s in statuses):
            icon = "❌"
        elif all(s == "AT" for s in statuses):
            icon = "⏰"
        elif all(s == "J" for s in statuses):
            icon = "✅"
        else:
            icon = "⚠️"
        lines.append(f"{icon} *{hora} — {subject_name}*")
        for name, status in sorted(students, key=lambda x: x[0]):
            lines.append(f"  {name} — {STATUS_ICON[status]} {STATUS_LABEL[status]}")
        lines.append("")
    return lines

MONTH_ES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

_SEP = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
_NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def _num_emoji(i: int) -> str:
    return _NUM_EMOJI[i - 1] if 1 <= i <= 10 else f"#{i}"


# ── Homework — curso único ─────────────────────────────────────────────────────


def format_homework(data: HomeworkData) -> str:
    """HTML — listado de tareas agrupadas por materia."""
    period = _period_label(data)
    total = len(data.records)
    open_count = sum(1 for hw in data.records if hw.is_open)
    closed_count = total - open_count

    lines = [
        "📋 <b>LISTADO DE TAREAS</b>",
        _SEP,
        f"🏫 <b>{_e(data.grade_name)}</b>  ·  {period}",
        f"📊 Total: {total} tareas  ·  🟢 Abiertas: {open_count}  ·  🔴 Cerradas: {closed_count}",
    ]

    if not total:
        lines += ["", "Sin tareas registradas en este período."]
        return "\n".join(lines)

    # Agrupar por materia preservando orden de aparición
    grouped: dict[str, list] = {}
    for hw in data.records:
        key = hw.subject or "Sin materia"
        grouped.setdefault(key, []).append(hw)

    # Índice de materias
    lines.append("")
    for subject, tasks in grouped.items():
        lines.append(f"▸ 📚 {_e(subject)} ({len(tasks)})")
    lines.append(_SEP)

    # Detalle por materia
    for subject, tasks in grouped.items():
        lines.append("")
        lines.append(f"📚 <b>{_e(subject)}</b>")
        for i, hw in enumerate(tasks, 1):
            lines.append(f"  {_num_emoji(i)} {_e(hw.description)}")

    return "\n".join(lines)


# ── Homework — multi-curso ─────────────────────────────────────────────────────


def format_homework_multi(data_list: list[HomeworkData], group_label: str = "Grupo") -> str:
    """HTML — listado de tareas agrupadas por curso y materia."""
    if not data_list:
        return "Sin tareas registradas."

    first = data_list[0]
    total = sum(len(d.records) for d in data_list)
    open_count = sum(1 for d in data_list for hw in d.records if hw.is_open)
    closed_count = total - open_count
    period = _period_label(first)

    lines = [
        "📋 <b>LISTADO DE TAREAS</b>",
        _SEP,
        f"🏫 <b>{_e(group_label)}</b>  ·  {period}",
        f"📊 Total: {total} tareas  ·  🟢 Abiertas: {open_count}  ·  🔴 Cerradas: {closed_count}",
        "",
    ]

    # Índice de cursos
    for data in data_list:
        n = len(data.records)
        lines.append(f"▸ 🏫 {_e(data.grade_name)} ({n})")
    lines.append(_SEP)

    for data in data_list:
        n = len(data.records)
        lines.append("")
        lines.append(f"🏫 <b>{_e(data.grade_name)}</b>")

        if not n:
            lines.append("  Sin tareas")
            continue

        grouped: dict[str, list] = {}
        for hw in data.records:
            key = hw.subject or "Sin materia"
            grouped.setdefault(key, []).append(hw)

        for subject, tasks in grouped.items():
            lines.append(f"  📚 <i>{_e(subject)}</i>")
            for i, hw in enumerate(tasks, 1):
                lines.append(f"    {_num_emoji(i)} {_e(hw.description)}")

    return "\n".join(lines)


# ── Attendance ─────────────────────────────────────────────────────────────────


def format_attendance(data: AttendanceData) -> str:
    header = _attendance_header(data)
    lines = [header, ""]

    proceed = data.total_students - len(data.records)

    if not data.records:
        lines.append("✅ Sin novedades — todos presentes")
    elif data.period_type == "day" and any(
        e.subject_name for rec in data.records for e in rec.entries
    ):
        # Consolidated view: grouped by period/subject
        lines.extend(_format_day_consolidated(data.records))
    else:
        for rec in data.records:
            has_subjects = any(e.subject_name for e in rec.entries)

            if data.period_type == "day":
                # Legacy: no subject info
                statuses = " | ".join(
                    f"{STATUS_ICON[e.status]} {STATUS_LABEL[e.status]}" for e in rec.entries
                )
                lines.append(f"{rec.student_name} — {statuses}")
            else:
                if has_subjects:
                    by_subj: dict[str, list[str]] = {}
                    for e in rec.entries:
                        key = e.subject_name or "—"
                        by_subj.setdefault(key, []).append(
                            f"{STATUS_ICON[e.status]}{e.date.strftime('%d/%m')}"
                        )
                    lines.append(f"⚠️ {rec.student_name}")
                    for subj, marks in by_subj.items():
                        lines.append(f"   {subj}: {' '.join(marks)}")
                else:
                    f_days = [str(e.date.day) for e in rec.entries if e.status == "F"]
                    at_days = [str(e.date.day) for e in rec.entries if e.status == "AT"]
                    j_days = [str(e.date.day) for e in rec.entries if e.status == "J"]
                    parts = []
                    if f_days:
                        parts.append(f"❌ F: {', '.join(f_days)}")
                    if at_days:
                        parts.append(f"⏰ AT: {', '.join(at_days)}")
                    if j_days:
                        parts.append(f"✅ J: {', '.join(j_days)}")
                    lines.append(f"{rec.student_name} → {' | '.join(parts)}")

    lines.append("")
    lines.append(f"Procede: {proceed} estudiantes")
    return "\n".join(lines)


# ── Attendance — multi-curso ───────────────────────────────────────────────────


def format_attendance_multi(data_list: list[AttendanceData], group_label: str = "Grupo") -> str:
    """Markdown — asistencia agrupada por curso."""
    if not data_list:
        return "Sin datos de asistencia."

    first = data_list[0]
    if first.period_type == "day":
        period = first.period_start.strftime("%d/%m/%Y")
    else:
        period = f"{first.period_start.strftime('%d/%m')}–{first.period_end.strftime('%d/%m/%Y')}"

    lines = [f"📊 *ASISTENCIA — {group_label}*", f"_{period}_", ""]

    for data in data_list:
        lines.append(f"*▸ {data.grade_name}*")
        if not data.records:
            lines.append("  ✅ Sin novedades")
        elif data.period_type == "day" and any(
            e.subject_name for rec in data.records for e in rec.entries
        ):
            for consolidated_line in _format_day_consolidated(data.records):
                lines.append(f"  {consolidated_line}")
        else:
            for rec in data.records:
                has_subjects = any(e.subject_name for e in rec.entries)
                if data.period_type == "day":
                    statuses = " | ".join(
                        f"{STATUS_ICON[e.status]} {STATUS_LABEL[e.status]}" for e in rec.entries
                    )
                    lines.append(f"  {rec.student_name} — {statuses}")
                elif has_subjects:
                    by_subj: dict[str, list[str]] = {}
                    for e in rec.entries:
                        key = e.subject_name or "—"
                        by_subj.setdefault(key, []).append(
                            f"{STATUS_ICON[e.status]}{e.date.strftime('%d/%m')}"
                        )
                    lines.append(f"  ⚠️ {rec.student_name}")
                    for subj, marks in by_subj.items():
                        lines.append(f"     {subj}: {' '.join(marks)}")
                else:
                    f_days = [str(e.date.day) for e in rec.entries if e.status == "F"]
                    at_days = [str(e.date.day) for e in rec.entries if e.status == "AT"]
                    j_days = [str(e.date.day) for e in rec.entries if e.status == "J"]
                    parts = []
                    if f_days:
                        parts.append(f"❌ F: {', '.join(f_days)}")
                    if at_days:
                        parts.append(f"⏰ AT: {', '.join(at_days)}")
                    if j_days:
                        parts.append(f"✅ J: {', '.join(j_days)}")
                    lines.append(f"  {rec.student_name} → {' | '.join(parts)}")
        lines.append("")

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



def _attendance_header(data: AttendanceData) -> str:
    if data.period_type == "day":
        period = data.period_start.strftime("%d/%m/%Y")
    elif data.period_type == "week":
        period = (
            f"Semana {data.period_start.strftime('%d/%m')}–{data.period_end.strftime('%d/%m/%Y')}"
        )
    elif data.period_type == "month":
        period = f"{MONTH_ES[data.period_start.month]} {data.period_start.year}"
    else:  # trimester
        period = (
            f"Trimestre {data.period_start.strftime('%d/%m')}"
            f"–{data.period_end.strftime('%d/%m/%Y')}"
        )
    return f"📋 *{data.grade_name} — {period}*"
