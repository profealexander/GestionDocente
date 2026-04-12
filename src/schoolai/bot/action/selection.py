"""Selección UI: keyboard, callbacks y dispatchers de opciones ambiguas."""

from __future__ import annotations

from datetime import date

from loguru import logger
from sqlalchemy import select
from telegram.constants import ParseMode

from schoolai.bot.action._widgets import _HW_STATUS_LABELS, _sel_keyboard
from schoolai.bot.action.notify import _reply_hw_report, _send_notify_prompt
from schoolai.bot.callback_router import callback_router
from schoolai.bot.state import (
    PendingSelection,
    clear_selection,
    get_selection,
    set_selection,
)
from schoolai.db.connection import get_db_session
from schoolai.db.models.homework import Homework
from schoolai.skills.attendance.service import save_absences
from schoolai.skills.homework.repository import count_students_in_grade, save_non_completers


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

    async with get_db_session() as session:
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


async def _sel_hw_task(user_id: int, hw_id: int, pending, bot) -> None:
    """Saves homework non-completion for the chosen task."""
    clear_selection(user_id)
    p = pending.payload

    async with get_db_session() as session:
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


async def _sel_hw_student(user_id: int, student_id: int, pending, bot) -> None:
    """Accumulates chosen student, then either asks next or proceeds to task step."""
    p = pending.payload
    item = p["queue"].pop(0)
    short = next(
        (c.get("short", c["name"]) for c in item["candidates"] if c["id"] == student_id),
        "Estudiante",
    )
    p["resolved_ids"].append(student_id)
    p["resolved_names"].append(short.title())

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

    student_ids = p["resolved_ids"]
    student_names = p["resolved_names"]
    not_found = p.get("not_found_names", [])
    status = p["status"]

    if p.get("hw_id") is not None:
        clear_selection(user_id)
        async with get_db_session() as session:
            hw = await session.get(Homework, p["hw_id"])
            if not hw:
                await bot.send_message(pending.chat_id, "Tarea no encontrada.")
                return
            await save_non_completers(session, p["hw_id"], student_ids, status)
            total = await count_students_in_grade(session, hw.grade_id)

        await _reply_hw_report(
            bot,
            pending.chat_id,
            hw,
            student_ids,
            student_names,
            not_found,
            status,
            total,
            user_id,
        )
        logger.info(
            f"[action] homework_report hw_student→direct user={user_id} "
            f"hw={p['hw_id']} missing={len(student_ids)}",
        )

    elif p.get("hw_ids"):
        clear_selection(user_id)
        async with get_db_session() as session:
            hws = (
                (await session.execute(select(Homework).where(Homework.id.in_(p["hw_ids"]))))
                .scalars()
                .all()
            )
            for hw in hws:
                await save_non_completers(session, hw.id, student_ids, status, commit=False)
            await session.commit()
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
