"""Ejecuta la acción correspondiente al resultado de extracción LLM."""

from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode

from schoolai.bot.callback_router import callback_router
from schoolai.bot.notif_handler import doc_notify_keyboard
from schoolai.bot.state import (
    PendingConfirm,
    PendingCourseContext,
    PendingSelection,
    PendingWhatsAppNotification,
    clear_course_context,
    clear_selection,
    get_course_context,
    get_jornada_context,
    get_selection,
    pop_pending_confirm,
    set_course_context,
    set_pending_confirm,
    set_selection,
    set_wa_notification,
)
from schoolai.bot.whatsapp_handler import notify_keyboard
from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.db.models.homework import Homework
from schoolai.skills.attendance.constants import ABSENT, JUSTIFIED, LATE
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.attendance.service import save_absences
from schoolai.skills.homework.repository import (
    count_students_in_grade,
    find_grade,
    find_homework_by_ref,
    find_subject,
    list_open,
    save_homework,
    save_non_completers,
)
from schoolai.skills.query.detector import QueryIntent, get_current_trimester
from schoolai.skills.utils.courses import course_abbrev_map
from schoolai.skills.utils.dates import (
    _DAY_NAMES,
)
from schoolai.skills.utils.dates import (
    parse_date as _parse_date,
)
from schoolai.skills.utils.dates import (
    resolve_delivery as _resolve_delivery,
)
from schoolai.skills.utils.keyboards import grade_keyboard
from schoolai.skills.utils.schema import (
    AttendanceExtract,
    ExtractionResult,
    HomeworkExtract,
    HomeworkReportExtract,
    QueryExtract,
)

# Caché ligero: datos parciales esperando que el usuario elija curso
# {user_id: ExtractionResult} — NO bloquea mensajes nuevos
_pending_cache: dict[int, ExtractionResult] = {}

STATUS_MAP = {
    "absent": ABSENT,
    "late": LATE,
    "justified": JUSTIFIED,
}

_HW_STATUS_LABELS: dict[str, str] = {
    "missing": "No entregaron",
    "late": "Entregaron tarde",
    "partial": "Entrega parcial",
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


@callback_router.register("sel:")
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
    p = pending.payload
    item = p["queue"].pop(0)
    short = next(
        (c.get("short", c["name"]) for c in item["candidates"] if c["id"] == student_id),
        "Estudiante",
    )
    attendance_date = date.fromisoformat(p["attendance_date"])
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
    status_label = _HW_STATUS_LABELS.get(p["status"], "No entregaron")
    missing = len(student_ids)
    lines = [f"📊 *CUMPLIMIENTO — Tarea #{hw.sequence_num}*", f"_{subj}_\n"]
    lines.append(f"✗ *{status_label} ({missing}):*")
    lines.extend(f"  • {name}" for name in p["student_names"])
    lines.append(f"\n✓ Cumplieron: *{max(0, total - missing)} de {total}*")
    if p.get("not_found_names"):
        lines.append(f"\n⚠️ No encontrados: {', '.join(p['not_found_names'])}")

    await bot.send_message(pending.chat_id, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    await _send_notify_prompt(
        lambda t, **kw: bot.send_message(pending.chat_id, t, **kw),
        user_id,
        hw,
        student_ids,
        p["student_names"],
    )
    logger.info(f"[action] homework_report via sel user={user_id} hw={hw_id} missing={missing}")


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
    student_ids = p["resolved_ids"]
    student_names = p["resolved_names"]
    not_found = p.get("not_found_names", [])
    status = p["status"]

    if p.get("hw_id") is not None:
        # Single known task — save directly
        clear_selection(user_id)
        async with async_session() as session:
            hw = await session.get(Homework, p["hw_id"])
            if not hw:
                await bot.send_message(pending.chat_id, "Tarea no encontrada.")
                return
            await save_non_completers(session, p["hw_id"], student_ids, status)
            total = await count_students_in_grade(session, hw.grade_id)

        await _reply_hw_report(
            bot, pending.chat_id, hw, student_ids, student_names, not_found, status, total, user_id,
        )
        logger.info(
            f"[action] homework_report hw_student→direct user={user_id} "
            f"hw={p['hw_id']} missing={len(student_ids)}",
        )

    elif p.get("hw_ids"):
        # Multiple known tasks — save to all
        clear_selection(user_id)
        async with async_session() as session:
            hws = (
                (await session.execute(select(Homework).where(Homework.id.in_(p["hw_ids"]))))
                .scalars()
                .all()
            )
            for hw in hws:
                await save_non_completers(session, hw.id, student_ids, status)
            total = await count_students_in_grade(session, p["grade_id"])

        status_label = _HW_STATUS_LABELS.get(status, "No entregaron")
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
            f"[action] homework_report hw_student→multi user={user_id} "
            f"tasks={len(hws)} missing={missing}",
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
                "student_ids": student_ids,
                "student_names": student_names,
                "not_found_names": not_found,
                "status": status,
                "grade_id": p["grade_id"],
                "chat_id": pending.chat_id,
            },
        )
        set_selection(user_id, task_pending)
        await bot.send_message(
            pending.chat_id,
            task_pending.prompt,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_sel_keyboard(task_options),
        )


async def _send_notify_prompt(
    send_fn, user_id: int, hw, student_ids: list, student_names: list,
) -> None:
    """Stores WA notification state and sends the notify button.

    send_fn must be an awaitable callable: send_fn(text, **kwargs).
    Typical usage:
      bot path  → lambda t, **kw: bot.send_message(chat_id, t, **kw)
      reply_fn  → update.message.reply_text
    """
    if not student_ids or not user_id:
        return
    delivery_str = hw.delivery_date.strftime("%d/%m/%Y") if hw.delivery_date else ""
    subj = hw.subject.name if hw.subject else "sin materia"
    set_wa_notification(
        user_id,
        PendingWhatsAppNotification(
            chat_id=0,  # not used; routing goes through bot.send_message in whatsapp_handler
            hw_id=hw.id,
            hw_seq=hw.sequence_num,
            subject=subj,
            grade_name=hw.grade.name if hw.grade else "",
            delivery_date=delivery_str,
            student_ids=list(student_ids),
            student_names=list(student_names),
        ),
    )
    await send_fn(
        "¿Deseas notificar a los representantes por WhatsApp?",
        reply_markup=notify_keyboard(student_ids),
    )
    await send_fn(
        "📄 Generar notificación formal:",
        reply_markup=doc_notify_keyboard(hw.id, student_ids, student_names),
    )


async def _reply_hw_report(
    bot, chat_id, hw, student_ids, student_names, not_found, status, total, user_id: int = 0,
):
    """Sends the homework report summary message and notify button."""
    subj = hw.subject.name if hw.subject else "sin materia"
    status_label = _HW_STATUS_LABELS.get(status, "No entregaron")
    missing = len(student_ids)
    lines = [f"📊 *CUMPLIMIENTO — Tarea #{hw.sequence_num}*", f"_{subj}_\n"]
    lines.append(f"✗ *{status_label} ({missing}):*")
    lines.extend(f"  • {name}" for name in student_names)
    lines.append(f"\n✓ Cumplieron: *{max(0, total - missing)} de {total}*")
    if not_found:
        lines.append(f"\n⚠️ No encontrados: {', '.join(not_found)}")
    await bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    await _send_notify_prompt(
        lambda t, **kw: bot.send_message(chat_id, t, **kw),
        user_id,
        hw,
        student_ids,
        student_names,
    )


# ── Attendance ────────────────────────────────────────────────────────────────


async def _handle_attendance(
    update, user_id: int, result: ExtractionResult, data: AttendanceExtract,
) -> None:
    if data.status == "all_present":
        att_date = _parse_date(data.date)
        course_str = (data.course or "el curso").upper()
        await update.message.reply_text(
            f"✅ *{course_str} — {att_date.strftime('%d/%m/%Y')}*\n"
            f"Asistencia completa — sin ausencias registradas.",
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info(f"[action] all_present user={user_id} course={data.course}")
        return

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
        ctx = get_course_context(user_id)
        if ctx and ctx.pending_intent == "attendance":
            data.course = ctx.grade_name
            data.complete = True
            clear_course_context(user_id)

    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (
                (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
            )
        names_preview = ", ".join(data.names[:3])
        if len(data.names) > 3:
            names_preview += f" y {len(data.names) - 3} más"
        await update.message.reply_text(
            f"Ausentes: *{names_preview}*\n\n¿De qué curso?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return

    from schoolai.config import settings
    from schoolai.skills.utils.dates import parse_date as _pd

    if result.via_llm or settings.supervised_mode:
        status_label = {"absent": "Falta", "late": "Atraso", "justified": "Justificado"}.get(
            data.status, "Falta",
        )
        names_preview = ", ".join(data.names[:5])
        if len(data.names) > 5:
            names_preview += f" y {len(data.names) - 5} más"
        att_date = _pd(data.date)
        set_pending_confirm(
            user_id,
            PendingConfirm(
                chat_id=update.message.chat_id,
                intent="attendance",
                summary=(
                    f"*{data.course}* — {att_date.strftime('%d/%m/%Y')}\n"
                    f"{status_label}: {names_preview}"
                ),
                data=data,
            ),
        )
        await update.message.reply_text(
            f"🤖 *Extracción automática — ¿es correcto?*\n\n"
            f"Curso: *{data.course}*\n"
            f"Fecha: *{att_date.strftime('%d/%m/%Y')}*\n"
            f"{status_label}: *{names_preview}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Confirmar", callback_data="act_confirm:yes"),
                        InlineKeyboardButton("❌ Cancelar", callback_data="act_confirm:no"),
                    ],
                ],
            ),
        )
        return

    await _save_attendance(update.message.reply_text, user_id, data, update.message.chat_id)


async def _save_attendance(
    reply_fn, user_id: int, data: AttendanceExtract, chat_id: int = 0,
) -> None:

    attendance_date = _parse_date(data.date)
    status = STATUS_MAP.get(data.status, ABSENT)
    extracted = [{"name": n, "status": status} for n in data.names]

    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        results = await match_names(extracted, grade.id, session)

    resolved = [r for r in results if r.resolved]
    ambiguous = [r for r in results if r.ambiguous]
    not_found = [r for r in results if r.not_found]

    # Guardar resueltos directo
    if resolved:
        student_ids = [r.matched_id for r in resolved]
        statuses = {r.matched_id: r.status for r in resolved}
        async with async_session() as session:
            await save_absences(student_ids, statuses, attendance_date, session)

    status_label = {"absent": "Faltas", "late": "Atrasos", "justified": "Justificados"}.get(
        data.status, "Faltas",
    )
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
            f"⚠️ *¿A cuál _{first['raw_name']}_ te refieres?*\n_Toca un botón o escribe el número:_"
        ),
        options=first_options,
        action="att_student",
        payload={
            "status": status,
            "attendance_date": attendance_date.isoformat(),
            "queue": queue,
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


async def _handle_homework(
    update, user_id: int, result: ExtractionResult, data: HomeworkExtract,
) -> None:
    if not data.course or not data.subject:
        grade_id, grade_name, subject_id, subject_name = get_jornada_context(user_id)
        if grade_name and not data.course:
            data.course = grade_name
        if subject_name and not data.subject:
            data.subject = subject_name
        if data.course and data.subject:
            data.complete = True

    if not data.course:
        ctx = get_course_context(user_id)
        if ctx and ctx.pending_intent == "homework":
            data.course = ctx.grade_name
            data.complete = True
            clear_course_context(user_id)

    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (
                (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
            )
        await update.message.reply_text(
            f"Tarea: *{data.description[:60]}*\n\n¿Para qué curso?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return

    if not data.subject and not data.subjects:
        data.subject = "Asignación"

    from schoolai.config import settings

    subjects_display = ", ".join(data.subjects) if data.subjects else data.subject
    if result.via_llm or settings.supervised_mode:
        desc_preview = data.description[:60]
        set_pending_confirm(
            user_id,
            PendingConfirm(
                chat_id=update.message.chat_id,
                intent="homework",
                summary=f"*{data.course}* — {subjects_display}\n_{desc_preview}_",
                data=data,
            ),
        )
        await update.message.reply_text(
            f"🤖 *Extracción automática — ¿es correcto?*\n\n"
            f"Curso: *{data.course}* | Materia: *{subjects_display}*\n"
            f"_{desc_preview}_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Confirmar", callback_data="act_confirm:yes"),
                        InlineKeyboardButton("❌ Cancelar", callback_data="act_confirm:no"),
                    ],
                ],
            ),
        )
        return

    await _save_homework(update.message.reply_text, user_id, data)


async def _save_homework(reply_fn, user_id: int, data: HomeworkExtract) -> None:
    from sqlalchemy import select as _select

    from schoolai.db.models.teacher import Teacher

    # Determinar lista de materias a crear
    subjects_list = data.subjects or ([data.subject] if data.subject else ["Asignación"])

    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        delivery = _resolve_delivery(data.delivery_date)

        from schoolai.bot.state import get_jornada as _get_jornada

        jornada = _get_jornada(user_id)
        teacher_id = jornada.teacher_id if jornada else None
        if not teacher_id:
            teacher_id = (
                await session.execute(
                    _select(Teacher.id).where(
                        Teacher.telegram_id == user_id, Teacher.is_active.is_(True),
                    ),
                )
            ).scalar_one_or_none()

        records: list[tuple] = []
        for subj_name in subjects_list:
            subj_obj = (
                await find_subject(session, subj_name)
                if subj_name and subj_name != "Asignación"
                else None
            )
            record = await save_homework(
                session,
                homework=data.description,
                grade_id=grade.id,
                subject_id=subj_obj.id if subj_obj else None,
                delivery_date=delivery,
                teacher_id=teacher_id,
            )
            records.append((record, subj_obj, subj_name))

    delivery_str = (
        records[0][0].delivery_date.strftime("%d/%m/%Y")
        if records[0][0].delivery_date
        else "no especificada"
    )

    if len(records) == 1:
        record, subj_obj, subj_name = records[0]
        subject_str = subj_obj.name if subj_obj else "sin materia"
        await reply_fn(
            f"✅ Tarea #{record.sequence_num} registrada\n"
            f"{subject_str} | {grade.name} | Trimestre {record.trimester_num}\n"
            f"Entrega: {delivery_str}",
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.info(f"[action] homework user={user_id} id={record.id}")
    else:
        lines = [
            f"✅ *{len(records)} tareas registradas* — "
            f"{grade.name} | Trimestre {records[0][0].trimester_num}",
        ]
        for record, subj_obj, subj_name in records:
            subj_label = subj_obj.name if subj_obj else subj_name
            lines.append(f"  • Tarea #{record.sequence_num} — {subj_label}")
        lines.append(f"Entrega: {delivery_str}")
        await reply_fn("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        logger.info(f"[action] homework user={user_id} ids={[r[0].id for r in records]}")


# ── Query ─────────────────────────────────────────────────────────────────────


def _build_query_intent(period: str, subject_filter: str | None = None):
    from schoolai.skills.query.detector import TRIMESTERS

    today = date.today()
    sf = subject_filter

    if period == "today":
        return QueryIntent("homework", "day", today, today, subject_filter=sf)
    if period == "yesterday":
        d = today - timedelta(days=1)
        return QueryIntent("homework", "day", d, d, subject_filter=sf)
    if period == "week":
        start = today - timedelta(days=today.weekday())
        return QueryIntent("homework", "week", start, start + timedelta(days=4), subject_filter=sf)
    if period == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        return QueryIntent("homework", "week", start, start + timedelta(days=4), subject_filter=sf)
    if period == "month":
        start = today.replace(day=1)
        return QueryIntent("homework", "month", start, today, subject_filter=sf)
    if period == "last_month":
        first = today.replace(day=1)
        end = first - timedelta(days=1)
        return QueryIntent("homework", "month", end.replace(day=1), end, subject_filter=sf)
    if period in ("trimester_1", "trimester_2", "trimester_3"):
        num = int(period[-1])
        _, start, end = TRIMESTERS[num - 1]
        return QueryIntent(
            "homework", "trimester", start, end, trimester_num=num, subject_filter=sf,
        )
    if period == "year":
        start = TRIMESTERS[0][1]
        end = TRIMESTERS[-1][2]
        return QueryIntent("homework", "year", start, end, subject_filter=sf)
    if period.startswith("month:"):
        try:
            month_num = int(period.split(":")[1])
            year = today.year if month_num <= today.month else today.year - 1
            start = date(year, month_num, 1)
            if month_num == 12:
                end = date(year, 12, 31)
            else:
                end = date(year, month_num + 1, 1) - timedelta(days=1)
            return QueryIntent("homework", "month", start, end, subject_filter=sf)
        except (ValueError, IndexError):
            pass
    # Nombre de día (lunes…viernes) → ocurrencia pasada más reciente
    if period.lower().strip() in _DAY_NAMES:
        d = _parse_date(period)
        return QueryIntent("homework", "day", d, d, subject_filter=sf)
    try:
        d = date.fromisoformat(period)
        return QueryIntent("homework", "day", d, d, subject_filter=sf)
    except ValueError:
        pass
    num, start, end = get_current_trimester()
    return QueryIntent("homework", "trimester", start, end, trimester_num=num, subject_filter=sf)


async def _handle_query(update, user_id: int, result: ExtractionResult, data: QueryExtract) -> None:
    from schoolai.bot.query_handler import _run_query
    from schoolai.skills.query.formatter import format_homework_multi
    from schoolai.skills.query.resolver import resolve_homework_multi

    if not data.courses:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (
                (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
            )
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
        label = " y ".join(
            data.courses[i].upper()
            for i in range(len(data.courses))
            if data.courses[i] in course_abbrev_map
        )
        text = format_homework_multi(data_list, label)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ── Confirmation callback (supervised_mode / via_llm) ────────────────────────


@callback_router.register("act_confirm:")
async def handle_act_confirm_callback(update, context) -> None:
    """Handles act_confirm:yes|no — confirma o cancela una acción extraída por LLM."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    choice = query.data.split(":")[1]  # "yes" | "no"

    pc = pop_pending_confirm(user_id)

    if choice == "no" or pc is None:
        await query.edit_message_text("❌ Operación cancelada.")
        return

    await query.edit_message_reply_markup(reply_markup=None)

    async def _reply(text, **kw):
        await context.bot.send_message(pc.chat_id, text, **kw)

    if pc.intent == "attendance":
        await _save_attendance(_reply, user_id, pc.data, pc.chat_id)
    elif pc.intent == "homework":
        await _save_homework(_reply, user_id, pc.data)


# ── Course action callback ────────────────────────────────────────────────────


@callback_router.register("course_action:")
async def handle_course_action_callback(update, context) -> None:
    """Handles course_action:{action}:{abbrev} — triggered from the course-only menu."""
    from schoolai.skills.utils.courses import _ABBREV_TO_NAME, course_abbrev_map

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    _, action, abbrev = query.data.split(":", 2)

    grade_id = course_abbrev_map.get(abbrev)
    if not grade_id:
        await query.edit_message_text("Curso no encontrado.")
        return

    grade_name = _ABBREV_TO_NAME.get(abbrev, abbrev.upper())
    await query.edit_message_reply_markup(reply_markup=None)

    if action in ("hw", "att", "compliance"):
        intent_map = {"hw": "homework", "att": "attendance", "compliance": "homework_report"}
        ctx = PendingCourseContext(
            course_abbrev=abbrev,
            grade_id=grade_id,
            grade_name=grade_name,
            pending_intent=intent_map[action],
        )
        set_course_context(user_id, ctx)
        prompts = {
            "hw": (
                f"¿Cuál es la tarea para <b>{grade_name.title()}</b>?\n"
                "<i>Indica también la materia.</i>"
            ),
            "att": f"¿Quién faltó hoy en <b>{grade_name.title()}</b>?",
            "compliance": (
                f"¿Quién no entregó en <b>{grade_name.title()}</b>?\n"
                "<i>Puedes indicar la tarea si aplica.</i>"
            ),
        }
        await context.bot.send_message(chat_id, prompts[action], parse_mode=ParseMode.HTML)

    elif action == "query_hw":
        intent = _build_query_intent("trimester")
        intent.type = "homework"
        from schoolai.bot.query_handler import _run_query

        await _run_query(
            lambda t, **kw: context.bot.send_message(chat_id, t, **kw),
            user_id,
            intent,
            grade_id,
        )

    elif action == "query_att":
        today = date.today()
        intent = QueryIntent(type="attendance", period="day", period_start=today, period_end=today)
        from schoolai.bot.query_handler import _run_query

        await _run_query(
            lambda t, **kw: context.bot.send_message(chat_id, t, **kw),
            user_id,
            intent,
            grade_id,
        )

    elif action == "pick":
        # Viene del menú de grupo (ej. "bachillerato" → eligió "1ro BT")
        # Muestra el menú de acciones para el curso elegido
        from schoolai.bot.handlers import _show_course_action_menu
        await _show_course_action_menu(update, (abbrev, grade_id, grade_name))


# ── Homework Report ───────────────────────────────────────────────────────────


async def _handle_homework_report(
    update, user_id: int, result: ExtractionResult, data: HomeworkReportExtract,
) -> None:
    if not data.course:
        ctx = get_course_context(user_id)
        if ctx and ctx.pending_intent == "homework_report":
            data.course = ctx.grade_name
            data.complete = True
            clear_course_context(user_id)

    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (
                (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
            )
        await update.message.reply_text(
            "¿De qué curso es el reporte?",
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return
    await _save_homework_report(update.message.reply_text, user_id, data, update.message.chat_id)


async def _save_homework_report(
    reply_fn, user_id: int, data: HomeworkReportExtract, chat_id: int = 0,
) -> None:

    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        subject = await find_subject(session, data.subject) if data.subject else None

        # ── Resolver nombres ──────────────────────────────────────────────────
        extracted = [{"name": n, "status": data.status} for n in data.names]
        name_results = await match_names(extracted, grade.id, session)
        resolved_names = [r for r in name_results if r.resolved]
        ambiguous_names = [r for r in name_results if r.ambiguous]
        not_found_names = [r for r in name_results if r.not_found]

        # ── Resolver tarea ────────────────────────────────────────────────────
        hw_resolved = None  # single Homework ORM object, or None
        hw_list = None  # list of Homework for "all open" case
        hw_options = None  # [{id, subject, date}] when ref not found

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
                        "id": t.id,
                        "subject": t.subject.name if t.subject else "Sin materia",
                        "date": t.delivery_date.strftime("%d/%m") if t.delivery_date else "",
                    }
                    for t in open_tasks
                ]

        elif subject:
            stmt = (
                select(Homework)
                .where(
                    Homework.grade_id == grade.id,
                    Homework.subject_id == subject.id,
                    Homework.is_open.is_(True),
                )
                .order_by(Homework.submission_date.desc())
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
                "queue": queue,
                "resolved_ids": [r.matched_id for r in resolved_names],
                "resolved_names": [r.matched_name for r in resolved_names],
                "not_found_names": [r.raw_name for r in not_found_names],
                "status": data.status,
                "grade_id": grade.id,
                "chat_id": chat_id,
                # task info:
                "hw_id": hw_resolved.id if hw_resolved else None,
                "hw_ids": [h.id for h in hw_list] if hw_list else None,
                "hw_options": hw_options,
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
        student_ids = [r.matched_id for r in resolved_names]
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
                    "student_ids": student_ids,
                    "student_names": student_names,
                    "not_found_names": not_found_strs,
                    "status": data.status,
                    "grade_id": grade.id,
                    "chat_id": chat_id,
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

        status_label = _HW_STATUS_LABELS.get(data.status, "No entregaron")

        total = await count_students_in_grade(session, grade.id)
        missing = len(student_ids)

        if len(homeworks) == 1:
            hw = homeworks[0]
            subj_name = hw.subject.name if hw.subject else "sin materia"
            lines = [
                f"📊 *CUMPLIMIENTO — Tarea #{hw.sequence_num}*",
                f"_{subj_name} / {grade.name}_\n",
            ]
        else:
            tareas_str = ", ".join(f"#{hw.sequence_num}" for hw in homeworks)
            lines = [
                f"📊 *CUMPLIMIENTO — Tareas {tareas_str}*",
                f"_{grade.name}_ (todas abiertas)\n",
            ]

        lines.append(f"✗ *{status_label} ({missing}):*")
        lines.extend(f"  • {r.matched_name}" for r in resolved_names)
        lines.append(f"\n✓ Cumplieron: *{max(0, total - missing)} de {total}*")

        if not_found_strs:
            lines.append(f"\n⚠️ No encontrados: {', '.join(not_found_strs)}")

        await reply_fn("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        if len(homeworks) == 1 and student_ids:
            await _send_notify_prompt(
                reply_fn,
                user_id,
                homeworks[0],
                student_ids,
                [r.matched_name for r in resolved_names],
            )

        # Recordar el curso para el próximo reporte sin tener que preguntar de nuevo
        if user_id:
            abbrev = next((k for k, v in course_abbrev_map.items() if v == grade.id), "")
            set_course_context(
                user_id,
                PendingCourseContext(
                    course_abbrev=abbrev,
                    grade_id=grade.id,
                    grade_name=grade.name,
                    pending_intent="homework_report",
                ),
            )

        logger.info(
            f"[action] homework_report user={user_id} grade={grade.id} "
            f"tasks={len(homeworks)} missing={missing}",
        )


# ── Callback: usuario eligió curso ────────────────────────────────────────────


@callback_router.register("act_grade:")
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
        await _save_homework_report(
            query.edit_message_text, user_id, result.data, query.message.chat_id,
        )
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
