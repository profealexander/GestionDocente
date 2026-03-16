"""Ejecuta la acción correspondiente al resultado de extracción LLM."""

from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode

from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.skills.attendance.constants import ABSENT, LATE, JUSTIFIED
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.attendance.service import save_absences
from schoolai.skills.extractor.llm import _parse_date, _resolve_delivery
from schoolai.skills.extractor.schema import (
    AttendanceExtract,
    ExtractionResult,
    HomeworkExtract,
    HomeworkReportExtract,
    QueryExtract,
)
from schoolai.skills.homework.repository import (
    find_grade,
    find_subject,
    save_homework,
    find_homework_by_ref,
    list_open,
    save_non_completers,
    count_students_in_grade,
)
from schoolai.skills.utils.keyboards import grade_keyboard
from schoolai.bot.state import (
    PendingSelection,
    clear_selection,
    get_jornada_context,
    get_selection,
    set_selection,
)

# Caché ligero: datos parciales esperando que el usuario elija curso
# {user_id: ExtractionResult} — NO bloquea mensajes nuevos
_pending_cache: dict[int, ExtractionResult] = {}

STATUS_MAP = {
    "absent": ABSENT,
    "late": LATE,
    "justified": JUSTIFIED,
}


def store_pending(user_id: int, result: ExtractionResult) -> None:
    _pending_cache[user_id] = result


def pop_pending(user_id: int) -> ExtractionResult | None:
    return _pending_cache.pop(user_id, None)


async def handle_extraction(update: Update, user_id: int, result: ExtractionResult) -> None:
    """Punto de entrada principal. Actúa según el resultado del extractor."""
    intent = result.intent
    data = result.data

    if intent == "attendance":
        await _handle_attendance(update, user_id, result, data)
    elif intent == "homework":
        await _handle_homework(update, user_id, result, data)
    elif intent == "homework_report":
        await _handle_homework_report(update, user_id, result, data)
    elif intent == "query":
        await _handle_query(update, user_id, result, data)
    else:
        # chat — manejado por el caller
        pass


# ── Unified selection keyboard & helpers ──────────────────────────────────────

def _sel_keyboard(options: list[dict]) -> InlineKeyboardMarkup:
    """Builds inline keyboard for any selection. ≤3 in one row, else one per row."""
    buttons = [
        InlineKeyboardButton(
            f"{i}. {opt['label']}",
            callback_data=f"sel:{opt['value']}",
        )
        for i, opt in enumerate(options, 1)
    ]
    rows = [buttons] if len(buttons) <= 3 else [[b] for b in buttons]
    return InlineKeyboardMarkup(rows)


async def handle_selection_callback(update, context) -> None:
    """Handles any sel:{value} inline keyboard tap."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    value = query.data.split(":", 1)[1]

    pending = get_selection(user_id)
    if not pending:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    await query.edit_message_reply_markup(reply_markup=None)
    await _dispatch_selection(user_id, value, pending, context.bot)


async def resolve_selection_text(update, user_id: int) -> bool:
    """Intercepts typed numbers to resolve pending selections.
    Returns True if handled (caller should return)."""
    pending = get_selection(user_id)
    if not pending:
        return False

    text = update.message.text.strip()
    if not text.isdigit():
        return False

    idx = int(text)
    if not (1 <= idx <= len(pending.options)):
        return False

    value = pending.options[idx - 1]["value"]

    class _FakeBot:
        async def send_message(self, chat_id, text, **kw):
            await update.message.reply_text(text, **kw)

    await _dispatch_selection(user_id, value, pending, _FakeBot())
    return True


async def _dispatch_selection(user_id: int, value: str, pending, bot) -> None:
    if pending.action == "att_student":
        await _sel_att_student(user_id, int(value), pending, bot)
    elif pending.action == "hw_task":
        await _sel_hw_task(user_id, int(value), pending, bot)
    elif pending.action == "hw_student":
        await _sel_hw_student(user_id, int(value), pending, bot)


# ── Selection action: attendance student ──────────────────────────────────────

async def _sel_att_student(user_id: int, student_id: int, pending, bot) -> None:
    """Saves attendance for the chosen student, advances the ambiguous queue."""
    from datetime import date as _date

    p = pending.payload
    item = p["queue"].pop(0)
    short = next(
        (c.get("short", c["name"]) for c in item["candidates"] if c["id"] == student_id),
        "Estudiante",
    )
    attendance_date = _date.fromisoformat(p["attendance_date"])
    status = p["status"]
    status_labels = {"F": "Falta", "AT": "Atraso", "J": "Justificado"}

    async with async_session() as session:
        await save_absences([student_id], {student_id: status}, attendance_date, session)

    label = status_labels.get(status, "Falta")
    await bot.send_message(pending.chat_id, f"✅ {short.title()} — {label} registrado.")

    if p["queue"]:
        next_item = p["queue"][0]
        next_options = [
            {"label": c.get("short", c["name"]).title(), "value": str(c["id"])}
            for c in next_item["candidates"]
        ]
        next_pending = PendingSelection(
            chat_id=pending.chat_id,
            prompt=(
                f"⚠️ *¿A cuál _{next_item['raw_name']}_ te refieres?*\n"
                "_Toca un botón o escribe el número:_"
            ),
            options=next_options,
            action="att_student",
            payload=p,
        )
        set_selection(user_id, next_pending)
        await bot.send_message(
            pending.chat_id,
            next_pending.prompt,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_sel_keyboard(next_options),
        )
    else:
        clear_selection(user_id)


# ── Selection action: homework task ───────────────────────────────────────────

async def _sel_hw_task(user_id: int, hw_id: int, pending, bot) -> None:
    """Saves homework non-completion for the chosen task."""
    from schoolai.db.models.homework import Homework

    clear_selection(user_id)
    p = pending.payload

    async with async_session() as session:
        hw = await session.get(Homework, hw_id)
        if not hw:
            await bot.send_message(pending.chat_id, "Tarea no encontrada.")
            return

        student_ids = p["student_ids"]
        if not student_ids:
            await bot.send_message(pending.chat_id, "No hay estudiantes para registrar.")
            return

        await save_non_completers(session, hw_id, student_ids, p["status"])
        total = await count_students_in_grade(session, hw.grade_id)

    subj = hw.subject.name if hw.subject else "sin materia"
    status_label = {
        "missing": "No entregaron",
        "late":    "Entregaron tarde",
        "partial": "Entrega parcial",
    }.get(p["status"], "No entregaron")
    missing = len(student_ids)
    lines = [f"📊 *CUMPLIMIENTO — Tarea #{hw.sequence_num}*", f"_{subj}_\n"]
    lines.append(f"✗ *{status_label} ({missing}):*")
    lines.extend(f"  • {name}" for name in p["student_names"])
    lines.append(f"\n✓ Cumplieron: *{max(0, total - missing)} de {total}*")
    if p.get("not_found_names"):
        lines.append(f"\n⚠️ No encontrados: {', '.join(p['not_found_names'])}")

    await bot.send_message(pending.chat_id, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    logger.info(
        f"[action] homework_report via sel user={user_id} hw={hw_id} missing={missing}"
    )


# ── Selection action: homework report student ─────────────────────────────────

async def _sel_hw_student(user_id: int, student_id: int, pending, bot) -> None:
    """Accumulates chosen student, then either asks next or proceeds to task step.

    Payload fields:
        queue          — remaining ambiguous items [{raw_name, candidates}]
        resolved_ids   — accumulated student ids
        resolved_names — accumulated student display names
        not_found_names — already-known not-found names
        status         — "missing"|"late"|"partial"
        grade_id
        chat_id
        hw_id          — int if task known, None if task also needs selection
        hw_ids         — list[int] if multiple known tasks (save to all), or None
        hw_options     — list of task dicts for selection, or None
    """
    p = pending.payload
    item = p["queue"].pop(0)
    short = next(
        (c.get("short", c["name"]) for c in item["candidates"] if c["id"] == student_id),
        "Estudiante",
    )
    p["resolved_ids"].append(student_id)
    p["resolved_names"].append(short.title())

    if p["queue"]:
        # More ambiguous students — ask next
        next_item = p["queue"][0]
        next_options = [
            {"label": c.get("short", c["name"]).title(), "value": str(c["id"])}
            for c in next_item["candidates"]
        ]
        next_pending = PendingSelection(
            chat_id=pending.chat_id,
            prompt=(
                f"⚠️ *¿A cuál _{next_item['raw_name']}_ te refieres?*\n"
                "_Toca un botón o escribe el número:_"
            ),
            options=next_options,
            action="hw_student",
            payload=p,
        )
        set_selection(user_id, next_pending)
        await bot.send_message(
            pending.chat_id,
            next_pending.prompt,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_sel_keyboard(next_options),
        )
        return

    # All students resolved — proceed to task step
    student_ids   = p["resolved_ids"]
    student_names = p["resolved_names"]
    not_found     = p.get("not_found_names", [])
    status        = p["status"]

    if p.get("hw_id") is not None:
        # Single known task — save directly
        clear_selection(user_id)
        from schoolai.db.models.homework import Homework
        async with async_session() as session:
            hw = await session.get(Homework, p["hw_id"])
            if not hw:
                await bot.send_message(pending.chat_id, "Tarea no encontrada.")
                return
            await save_non_completers(session, p["hw_id"], student_ids, status)
            total = await count_students_in_grade(session, hw.grade_id)

        await _reply_hw_report(bot, pending.chat_id, hw, student_ids, student_names, not_found, status, total)
        logger.info(
            f"[action] homework_report hw_student→direct user={user_id} hw={p['hw_id']} missing={len(student_ids)}"
        )

    elif p.get("hw_ids"):
        # Multiple known tasks — save to all
        clear_selection(user_id)
        from schoolai.db.models.homework import Homework
        async with async_session() as session:
            hws = []
            for hw_id in p["hw_ids"]:
                hw = await session.get(Homework, hw_id)
                if hw:
                    hws.append(hw)
                    await save_non_completers(session, hw_id, student_ids, status)
            total = await count_students_in_grade(session, p["grade_id"])

        status_label = {
            "missing": "No entregaron", "late": "Entregaron tarde", "partial": "Entrega parcial",
        }.get(status, "No entregaron")
        tareas_str = ", ".join(f"#{hw.sequence_num}" for hw in hws)
        missing = len(student_ids)
        lines = [f"📊 *CUMPLIMIENTO — Tareas {tareas_str}*", "(todas abiertas)\n"]
        lines.append(f"✗ *{status_label} ({missing}):*")
        lines.extend(f"  • {name}" for name in student_names)
        lines.append(f"\n✓ Cumplieron: *{max(0, total - missing)} de {total}*")
        if not_found:
            lines.append(f"\n⚠️ No encontrados: {', '.join(not_found)}")
        await bot.send_message(pending.chat_id, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        logger.info(
            f"[action] homework_report hw_student→multi user={user_id} tasks={len(hws)} missing={missing}"
        )

    else:
        # Task unknown — chain to hw_task selection
        hw_options = p["hw_options"]
        task_options = [
            {
                "label": opt["subject"] + (f" — {opt['date']}" if opt.get("date") else ""),
                "value": str(opt["id"]),
            }
            for opt in hw_options
        ]
        task_pending = PendingSelection(
            chat_id=pending.chat_id,
            prompt="⚠️ *¿A qué tarea te refieres?*\n_Toca un botón o escribe el número:_",
            options=task_options,
            action="hw_task",
            payload={
                "student_ids":    student_ids,
                "student_names":  student_names,
                "not_found_names": not_found,
                "status":         status,
                "grade_id":       p["grade_id"],
                "chat_id":        pending.chat_id,
            },
        )
        set_selection(user_id, task_pending)
        await bot.send_message(
            pending.chat_id,
            task_pending.prompt,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_sel_keyboard(task_options),
        )


async def _reply_hw_report(bot, chat_id, hw, student_ids, student_names, not_found, status, total):
    """Sends the homework report summary message."""
    subj = hw.subject.name if hw.subject else "sin materia"
    status_label = {
        "missing": "No entregaron", "late": "Entregaron tarde", "partial": "Entrega parcial",
    }.get(status, "No entregaron")
    missing = len(student_ids)
    lines = [f"📊 *CUMPLIMIENTO — Tarea #{hw.sequence_num}*", f"_{subj}_\n"]
    lines.append(f"✗ *{status_label} ({missing}):*")
    lines.extend(f"  • {name}" for name in student_names)
    lines.append(f"\n✓ Cumplieron: *{max(0, total - missing)} de {total}*")
    if not_found:
        lines.append(f"\n⚠️ No encontrados: {', '.join(not_found)}")
    await bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ── Attendance ────────────────────────────────────────────────────────────────

async def _handle_attendance(update, user_id: int, result: ExtractionResult, data: AttendanceExtract) -> None:
    if not data.names:
        await update.message.reply_text(
            "Entendí que es asistencia pero no identifiqué nombres.\n"
            "_Ejemplo: Hoy faltaron Juan Pérez y María López del 3ro BT._",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not data.course:
        grade_id, grade_name, _, _ = get_jornada_context(user_id)
        if grade_name:
            data.course = grade_name
            data.complete = True

    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
        names_preview = ", ".join(data.names[:3])
        if len(data.names) > 3:
            names_preview += f" y {len(data.names) - 3} más"
        await update.message.reply_text(
            f"Ausentes: *{names_preview}*\n\n¿De qué curso?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return

    await _save_attendance(update.message.reply_text, user_id, data, update.message.chat_id)


async def _save_attendance(reply_fn, user_id: int, data: AttendanceExtract, chat_id: int = 0) -> None:

    attendance_date = _parse_date(data.date)
    status = STATUS_MAP.get(data.status, ABSENT)
    extracted = [{"name": n, "status": status} for n in data.names]

    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        results = await match_names(extracted, grade.id, session)

    resolved  = [r for r in results if r.resolved]
    ambiguous = [r for r in results if r.ambiguous]
    not_found = [r for r in results if r.not_found]

    # Guardar resueltos directo
    if resolved:
        student_ids = [r.matched_id for r in resolved]
        statuses = {r.matched_id: r.status for r in resolved}
        async with async_session() as session:
            await save_absences(student_ids, statuses, attendance_date, session)

    status_label = {"absent": "Faltas", "late": "Atrasos", "justified": "Justificados"}.get(data.status, "Faltas")
    lines = [f"📋 *{data.course} — {attendance_date.strftime('%d/%m/%Y')}*\n"]

    if resolved:
        lines.append(f"✅ *{status_label} registrados ({len(resolved)})*")
        lines.extend(f"  • {r.matched_name}" for r in resolved)

    if not_found:
        lines.append("\n❌ *No encontrados*")
        lines.extend(f"  • {r.raw_name}" for r in not_found)

    logger.info(f"[action] attendance user={user_id} saved={len(resolved)}")

    if not ambiguous:
        await reply_fn("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        return

    # Hay ambiguos: mostrar primera pregunta con botones
    queue = [{"raw_name": r.raw_name, "candidates": r.candidates} for r in ambiguous]
    first = queue[0]
    first_options = [
        {"label": c.get("short", c["name"]).title(), "value": str(c["id"])}
        for c in first["candidates"]
    ]
    pending = PendingSelection(
        chat_id=chat_id,
        prompt=(
            f"⚠️ *¿A cuál _{first['raw_name']}_ te refieres?*\n"
            "_Toca un botón o escribe el número:_"
        ),
        options=first_options,
        action="att_student",
        payload={
            "status":          status,
            "attendance_date": attendance_date.isoformat(),
            "queue":           queue,
        },
    )
    set_selection(user_id, pending)

    lines.append(f"\n⚠️ *¿A cuál _{first['raw_name']}_ te refieres?*")
    lines.append("_Toca un botón o escribe el número:_")

    await reply_fn(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_sel_keyboard(first_options),
    )


# ── Homework ──────────────────────────────────────────────────────────────────

async def _handle_homework(update, user_id: int, result: ExtractionResult, data: HomeworkExtract) -> None:
    if not data.course or not data.subject:
        grade_id, grade_name, subject_id, subject_name = get_jornada_context(user_id)
        if grade_name and not data.course:
            data.course = grade_name
        if subject_name and not data.subject:
            data.subject = subject_name
        if data.course and data.subject:
            data.complete = True

    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
        await update.message.reply_text(
            f"Tarea: *{data.description[:60]}*\n\n¿Para qué curso?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return

    await _save_homework(update.message.reply_text, user_id, data)


async def _save_homework(reply_fn, user_id: int, data: HomeworkExtract) -> None:
    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        subject = await find_subject(session, data.subject) if data.subject else None
        delivery = _resolve_delivery(data.delivery_date)

        record = await save_homework(
            session,
            homework=data.description,
            grade_id=grade.id,
            subject_id=subject.id if subject else None,
            delivery_date=delivery,
        )

    delivery_str = record.delivery_date.strftime("%d/%m/%Y") if record.delivery_date else "no especificada"
    subject_str = subject.name if subject else "sin materia"
    await reply_fn(
        f"✅ Tarea #{record.sequence_num} registrada\n"
        f"{subject_str} | {grade.name} | Trimestre {record.trimester_num}\n"
        f"Entrega: {delivery_str}",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f"[action] homework user={user_id} id={record.id}")


# ── Query ─────────────────────────────────────────────────────────────────────

def _build_query_intent(period: str, subject_filter: str | None = None):
    from schoolai.skills.query.detector import QueryIntent, get_current_trimester
    today = date.today()
    if period == "today":
        return QueryIntent("homework", "day", today, today, subject_filter=subject_filter)
    if period == "yesterday":
        d = today - timedelta(days=1)
        return QueryIntent("homework", "day", d, d, subject_filter=subject_filter)
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return QueryIntent("homework", "week", start, start + timedelta(days=4), subject_filter=subject_filter)
    if period == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        return QueryIntent("homework", "week", start, start + timedelta(days=4), subject_filter=subject_filter)
    if period == "month":
        start = today.replace(day=1)
        return QueryIntent("homework", "month", start, today, subject_filter=subject_filter)
    if period == "last_month":
        first = today.replace(day=1)
        end = first - timedelta(days=1)
        return QueryIntent("homework", "month", end.replace(day=1), end, subject_filter=subject_filter)
    num, start, end = get_current_trimester()
    return QueryIntent("homework", "trimester", start, end, trimester_num=num, subject_filter=subject_filter)


async def _handle_query(update, user_id: int, result: ExtractionResult, data: QueryExtract) -> None:
    from schoolai.bot.query_handler import _run_query
    from schoolai.skills.extractor.llm import course_abbrev_map
    from schoolai.skills.query.formatter import format_homework_multi
    from schoolai.skills.query.resolver import resolve_homework_multi

    if not data.courses:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
        await update.message.reply_text(
            "¿De qué curso quieres la consulta?",
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return

    intent = _build_query_intent(data.period, data.subject)
    intent.type = data.query_type

    # Resolver abreviaturas → grade_ids
    grade_ids = [course_abbrev_map[c] for c in data.courses if c in course_abbrev_map]
    if not grade_ids:
        await update.message.reply_text(
            f"No reconocí los cursos: {', '.join(data.courses)}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if len(grade_ids) == 1:
        await _run_query(update.message.reply_text, user_id, intent, grade_ids[0])
    else:
        async with async_session() as session:
            data_list = await resolve_homework_multi(intent, grade_ids, session)
        label = " y ".join(data.courses[i].upper() for i in range(len(data.courses)) if data.courses[i] in course_abbrev_map)
        text = format_homework_multi(data_list, label)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ── Homework Report ───────────────────────────────────────────────────────────

async def _handle_homework_report(update, user_id: int, result: ExtractionResult, data: HomeworkReportExtract) -> None:
    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
        await update.message.reply_text(
            "¿De qué curso es el reporte?",
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return
    await _save_homework_report(update.message.reply_text, user_id, data, update.message.chat_id)


async def _save_homework_report(reply_fn, user_id: int, data: HomeworkReportExtract, chat_id: int = 0) -> None:

    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        subject = await find_subject(session, data.subject) if data.subject else None

        # ── Resolver nombres ──────────────────────────────────────────────────
        extracted = [{"name": n, "status": data.status} for n in data.names]
        name_results   = await match_names(extracted, grade.id, session)
        resolved_names = [r for r in name_results if r.resolved]
        ambiguous_names = [r for r in name_results if r.ambiguous]
        not_found_names = [r for r in name_results if r.not_found]

        # ── Resolver tarea ────────────────────────────────────────────────────
        hw_resolved = None   # single Homework ORM object, or None
        hw_list     = None   # list of Homework for "all open" case
        hw_options  = None   # [{id, subject, date}] when ref not found

        if data.homework_ref is not None:
            hw_resolved = await find_homework_by_ref(
                session,
                sequence_num=data.homework_ref,
                grade_id=grade.id,
                subject_id=subject.id if subject else None,
            )
            if hw_resolved is None:
                open_tasks = await list_open(session, grade.id)
                if not open_tasks:
                    await reply_fn(
                        f"No hay tareas abiertas para *{grade.name}*.",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return
                hw_options = [
                    {
                        "id":      t.id,
                        "subject": t.subject.name if t.subject else "Sin materia",
                        "date":    t.delivery_date.strftime("%d/%m") if t.delivery_date else "",
                    }
                    for t in open_tasks
                ]

        elif subject:
            from schoolai.db.models.homework import Homework as _HW
            stmt = (
                select(_HW)
                .where(_HW.grade_id == grade.id, _HW.subject_id == subject.id, _HW.is_open.is_(True))
                .order_by(_HW.submission_date.desc())
                .limit(1)
            )
            hw_resolved = (await session.execute(stmt)).scalars().first()
            if not hw_resolved:
                await reply_fn(
                    f"No hay tareas abiertas de *{subject.name}* para *{grade.name}*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

        else:
            # Sin número ni materia → todas las tareas abiertas del curso
            hw_list = await list_open(session, grade.id)
            if not hw_list:
                await reply_fn(
                    f"No hay tareas abiertas para *{grade.name}*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

        # ── Dispatcher: 4 quadrants (names × task) ───────────────────────────

        if ambiguous_names:
            # Need to resolve students first; task info carried in payload
            queue = [{"raw_name": r.raw_name, "candidates": r.candidates} for r in ambiguous_names]
            first = queue[0]
            first_options = [
                {"label": c.get("short", c["name"]).title(), "value": str(c["id"])}
                for c in first["candidates"]
            ]
            payload: dict = {
                "queue":           queue,
                "resolved_ids":    [r.matched_id for r in resolved_names],
                "resolved_names":  [r.matched_name for r in resolved_names],
                "not_found_names": [r.raw_name for r in not_found_names],
                "status":          data.status,
                "grade_id":        grade.id,
                "chat_id":         chat_id,
                # task info:
                "hw_id":           hw_resolved.id if hw_resolved else None,
                "hw_ids":          [h.id for h in hw_list] if hw_list else None,
                "hw_options":      hw_options,
            }
            pending = PendingSelection(
                chat_id=chat_id,
                prompt=(
                    f"⚠️ *¿A cuál _{first['raw_name']}_ te refieres?*\n"
                    "_Toca un botón o escribe el número:_"
                ),
                options=first_options,
                action="hw_student",
                payload=payload,
            )
            set_selection(user_id, pending)
            await reply_fn(
                pending.prompt,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_sel_keyboard(first_options),
            )
            return

        # Names resolved — check task
        student_ids   = [r.matched_id for r in resolved_names]
        student_names = [r.matched_name for r in resolved_names]
        not_found_strs = [r.raw_name for r in not_found_names]

        if hw_options is not None:
            # Task unknown — show task selection
            task_options = [
                {
                    "label": opt["subject"] + (f" — {opt['date']}" if opt.get("date") else ""),
                    "value": str(opt["id"]),
                }
                for opt in hw_options
            ]
            pending = PendingSelection(
                chat_id=chat_id,
                prompt=(
                    f"⚠️ No encontré la tarea *#{data.homework_ref}* en *{grade.name}*.\n"
                    "¿A cuál te refieres?\n_Toca un botón o escribe el número:_"
                ),
                options=task_options,
                action="hw_task",
                payload={
                    "student_ids":    student_ids,
                    "student_names":  student_names,
                    "not_found_names": not_found_strs,
                    "status":         data.status,
                    "grade_id":       grade.id,
                    "chat_id":        chat_id,
                },
            )
            set_selection(user_id, pending)
            await reply_fn(
                pending.prompt,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_sel_keyboard(task_options),
            )
            return

        # Names resolved and task known — save directly
        homeworks = [hw_resolved] if hw_resolved else hw_list

        if student_ids:
            for hw in homeworks:
                await save_non_completers(session, hw.id, student_ids, data.status)

        status_label = {
            "missing": "No entregaron",
            "late":    "Entregaron tarde",
            "partial": "Entrega parcial",
        }.get(data.status, "No entregaron")

        total   = await count_students_in_grade(session, grade.id)
        missing = len(student_ids)

        if len(homeworks) == 1:
            hw = homeworks[0]
            subj_name = hw.subject.name if hw.subject else "sin materia"
            lines = [f"📊 *CUMPLIMIENTO — Tarea #{hw.sequence_num}*", f"_{subj_name} / {grade.name}_\n"]
        else:
            tareas_str = ", ".join(f"#{hw.sequence_num}" for hw in homeworks)
            lines = [f"📊 *CUMPLIMIENTO — Tareas {tareas_str}*", f"_{grade.name}_ (todas abiertas)\n"]

        lines.append(f"✗ *{status_label} ({missing}):*")
        lines.extend(f"  • {r.matched_name}" for r in resolved_names)
        lines.append(f"\n✓ Cumplieron: *{max(0, total - missing)} de {total}*")

        if not_found_strs:
            lines.append(f"\n⚠️ No encontrados: {', '.join(not_found_strs)}")

        await reply_fn("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        logger.info(
            f"[action] homework_report user={user_id} grade={grade.id} tasks={len(homeworks)} missing={missing}"
        )


# ── Callback: usuario eligió curso ────────────────────────────────────────────

async def handle_act_callback(update, context) -> None:
    """Maneja selección de curso cuando el extractor no lo detectó."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data  # "act_grade:{id}:{name}"

    parts = data.split(":", 2)
    grade_name = parts[2] if len(parts) > 2 else parts[1]

    result = pop_pending(user_id)
    if not result:
        await query.edit_message_text("Sesión expirada. Vuelve a enviar el mensaje.")
        return

    # Completar con el curso seleccionado
    if result.intent == "attendance":
        result.data.course = grade_name
        result.data.complete = True
        await _save_attendance(query.edit_message_text, user_id, result.data, query.message.chat_id)
    elif result.intent == "homework":
        result.data.course = grade_name
        result.data.complete = True
        await _save_homework(query.edit_message_text, user_id, result.data)
    elif result.intent == "homework_report":
        result.data.course = grade_name
        result.data.complete = True
        await _save_homework_report(query.edit_message_text, user_id, result.data, query.message.chat_id)
    elif result.intent == "query":
        from schoolai.bot.query_handler import _run_query
        from schoolai.skills.homework.repository import find_grade as _find_grade

        intent_obj = _build_query_intent(result.data.period, result.data.subject)
        intent_obj.type = result.data.query_type
        async with async_session() as session:
            grade = await _find_grade(session, grade_name)
        if grade:
            await _run_query(query.edit_message_text, user_id, intent_obj, grade.id)
        else:
            await query.edit_message_text(f"No encontré el curso {grade_name}.")
