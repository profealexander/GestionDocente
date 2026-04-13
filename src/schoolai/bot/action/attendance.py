"""Handlers de asistencia: _handle_attendance y _save_attendance."""

from __future__ import annotations


from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.bot.action._widgets import STATUS_MAP, _sel_keyboard
from schoolai.bot.action.cache import store_pending
from schoolai.bot.state import (
    PendingConfirm,
    PendingSelection,
    clear_course_context,
    get_course_context,
    get_jornada_context,
    set_pending_confirm,
    set_selection,
)
from schoolai.db.connection import get_db_session
from schoolai.db.models.grade import Grade
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.attendance.service import save_absences
from schoolai.skills.homework.repository import find_grade
from schoolai.skills.utils.keyboards import grade_keyboard
from schoolai.skills.utils.schema import AttendanceExtract, ExtractionResult


async def _handle_attendance(
    update,
    user_id: int,
    result: ExtractionResult,
    data: AttendanceExtract,
) -> None:
    if data.status == "all_present":
        att_date = _pd(data.date)
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
            result.via_llm = False

    if not data.course:
        ctx = get_course_context(user_id)
        if ctx and ctx.pending_intent == "attendance":
            data.course = ctx.grade_name
            data.complete = True
            clear_course_context(user_id)

    if not data.course:
        store_pending(user_id, result)
        async with get_db_session() as session:
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
    from schoolai.skills.utils.dates import parse_date as _parse_date_local

    if settings.supervised_mode:
        status_label = {"absent": "Falta", "late": "Atraso", "justified": "Justificado"}.get(
            data.status,
            "Falta",
        )
        names_preview = ", ".join(data.names[:5])
        if len(data.names) > 5:
            names_preview += f" y {len(data.names) - 5} más"
        att_date = _parse_date_local(data.date)
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


def _pd(date_str):
    from schoolai.skills.utils.dates import parse_date

    return parse_date(date_str)


async def _save_attendance(
    reply_fn,
    user_id: int,
    data: AttendanceExtract,
    chat_id: int = 0,
) -> None:
    from datetime import timedelta as _timedelta

    from sqlalchemy import select as _sel

    from schoolai.bot.state import get_jornada as _get_jornada
    from schoolai.db.models.teacher import Teacher as _Teacher
    from schoolai.skills.attendance.service import infer_period_from_schedule
    from schoolai.skills.utils.dates import parse_date as _parse_date

    # En Modo Jornada, usar la fecha de la sesión (no date.today()) para que el
    # registro sea correcto aunque el docente registre fuera del horario real
    # o la sesión persista pasada la medianoche.
    _jornada = _get_jornada(user_id)
    _jornada_session_date = _jornada.session_date if _jornada else None

    if data.date == "today" and _jornada_session_date is not None:
        attendance_date = _jornada_session_date
    elif data.date == "yesterday" and _jornada_session_date is not None:
        attendance_date = _jornada_session_date - _timedelta(days=1)
    else:
        attendance_date = _parse_date(data.date)
    status = STATUS_MAP.get(data.status, STATUS_MAP["absent"])
    extracted = [{"name": n, "status": status} for n in data.names]

    async with get_db_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        results = await match_names(extracted, grade.id, session)

    resolved = [r for r in results if r.resolved]
    ambiguous = [r for r in results if r.ambiguous]
    not_found = [r for r in results if r.not_found]

    if resolved:
        student_ids = [r.matched_id for r in resolved]
        statuses = {r.matched_id: r.status for r in resolved}

        # Reusar _jornada ya obtenido arriba
        _period = _jornada.current_period if _jornada else None
        _subject_name = _period.get("subject_name") if _period else None
        _period_start = _period.get("start_time") if _period else None
        _period_end = _period.get("end_time") if _period else None

        async with get_db_session() as session:
            if _subject_name is None:
                _teacher = (
                    await session.execute(_sel(_Teacher).where(_Teacher.telegram_id == user_id))
                ).scalar_one_or_none()
                if _teacher:
                    _subject_name, _period_start, _period_end = await infer_period_from_schedule(
                        session, _teacher.id, grade.id
                    )

            await save_absences(
                student_ids,
                statuses,
                attendance_date,
                session,
                subject_name=_subject_name,
                period_start=_period_start,
                period_end=_period_end,
            )

    status_label = {"absent": "Faltas", "late": "Atrasos", "justified": "Justificados"}.get(
        data.status,
        "Faltas",
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

    # Ambiguous — show first question with buttons
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
