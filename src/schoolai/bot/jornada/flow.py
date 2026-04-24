"""Máquina de estados y handlers del Modo Jornada."""

from datetime import date, timedelta

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.handlers import JORNADA_KEYBOARD, REMOVE_KEYBOARD
from schoolai.bot.sop import SOPEngine
from schoolai.bot.state import (
    JornadaSession,
    clear_jornada,
    get_jornada,
    set_jornada,
)
from schoolai.db.connection import get_db_session
from schoolai.skills.db.schedule_service import get_schedule_for_day, get_teacher_by_telegram
from schoolai.bot.jornada.card import _finish_jornada, _send_period_card
from schoolai.bot.jornada.helpers import _build_period_list, _current_period_index, _hora_label
from schoolai.bot.jornada.keyboards import (
    _ABSENT_DAY_REASON_KEYBOARD,
    _ABSENT_REASON_KEYBOARD,
    _ABSENT_REASONS,
    _FINISHED_KEYBOARD,
    _active_keyboard,
    day_pick_keyboard,
)

# ── SOP ───────────────────────────────────────────────────────────────────────

_JORNADA_SOP: SOPEngine | None = None


def _build_sop() -> SOPEngine:
    return SOPEngine(
        {
            ("*",       "jor_start"):   _on_start,
            ("waiting", "jor_here"):    _on_here,
            ("waiting", "jor_skip"):    _on_skip,
            ("waiting", "jor_back"):    _on_back,
            ("waiting", "jor_absent"):  _on_absent_menu,
            ("waiting", "jor_pause"):   _on_pause,
            ("waiting", "jor_end"):     _on_end,
            ("active",  "jor_next"):    _on_next,
            ("active",  "jor_back"):    _on_back,
            ("active",  "jor_pause"):   _on_pause,
            ("active",  "jor_end"):     _on_end,
            ("paused",  "jor_resume"):  _on_resume,
            ("paused",  "jor_end"):     _on_end,
            ("done",    "jor_restart"): _on_restart,
            ("done",    "jor_pick"):    _on_pick,
            ("*",       "jor_restart"): _on_restart,
            ("*",       "jor_pick"):    _on_pick,
        },
    )


# ── Comando /jornada ──────────────────────────────────────────────────────────


async def handle_jornada_command(update, context) -> None:
    """Permite iniciar Modo Jornada manualmente en cualquier momento."""
    user_id = update.effective_user.id
    session_obj = get_jornada(user_id)

    if session_obj and session_obj.status != "done":
        await _send_period_card(context.bot, session_obj, user_id)
        return

    raw_today = date.today().weekday()
    # Fin de semana → usar viernes como día de referencia para el horario
    today = raw_today if raw_today <= 4 else 4
    is_weekend = raw_today > 4

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await update.message.reply_text(
                "No tienes un perfil de docente vinculado.\n"
                "Usa /db → 📅 Horario para configurarlo.",
            )
            return
        periods = await get_schedule_for_day(session, teacher.id, today)

    if not periods:
        from schoolai.bot.state import DAY_NAMES
        # Sin horario: mostrar teclado de jornada terminada para que pueda
        # usar «Cambiar día» y seleccionar el día que necesita registrar.
        await update.message.reply_text(
            "📋 *No hay horario cargado para este día.*\n\n"
            "Usa *«Cambiar día»* para seleccionar el día que quieres registrar.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_FINISHED_KEYBOARD,
        )
        return

    period_list = _build_period_list(periods)
    # En fin de semana siempre modo "done" (retroactivo); en semana, detectar período actual
    start_index = len(period_list) if is_weekend else _current_period_index(period_list)

    # session_date: hoy para días de semana; último viernes para fin de semana
    real_today = date.today()
    if is_weekend:
        days_to_friday = (real_today.weekday() - 4) % 7  # sábado→1, domingo→2
        session_date = real_today - timedelta(days=days_to_friday)
    else:
        session_date = real_today

    if start_index >= len(period_list):
        from schoolai.bot.state import DAY_NAMES
        if is_weekend:
            msg = (
                f"📅 *Hoy es fin de semana.*\n\n"
                f"Cargué el horario del *{DAY_NAMES[today]}*.\n"
                "_Usa «Seleccionar período» para registrar o «Cambiar día» para otro día._"
            )
        else:
            msg = "✅ *Todos los períodos de hoy ya pasaron.*\n\n¿Qué deseas hacer?"
        await update.message.reply_text(
            msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_FINISHED_KEYBOARD,
        )
        jornada = JornadaSession(
            teacher_id=teacher.id,
            chat_id=update.message.chat_id,
            day_of_week=today,
            periods=period_list,
            current_index=len(period_list) - 1,
            status="done",
            session_date=session_date,
        )
        set_jornada(user_id, jornada)
        return

    jornada = JornadaSession(
        teacher_id=teacher.id,
        chat_id=update.message.chat_id,
        day_of_week=today,
        periods=period_list,
        current_index=start_index,
        session_date=session_date,
    )
    set_jornada(user_id, jornada)
    await _send_period_card(context.bot, jornada, user_id)


# ── Callback dispatcher ───────────────────────────────────────────────────────


async def handle_jornada_callback(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _JORNADA_SOP
    if _JORNADA_SOP is None:
        _JORNADA_SOP = _build_sop()

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data == "jor_day_pick":
        await _on_day_pick(query, user_id)
        return
    if data.startswith("jor_day:"):
        await _on_day_select(query, user_id, int(data.split(":")[1]), context)
        return
    if data.startswith("jor_goto:"):
        await _on_goto(query, user_id, int(data.split(":")[1]), context)
        return
    if data.startswith("jor_absent_reason:"):
        await _on_absent_reason(query, user_id, data.split(":", 1)[1], context)
        return
    if data == "jor_absent_day":
        await _on_absent_day(query, user_id, context)
        return
    if data.startswith("jor_absent_day_reason:"):
        await _on_absent_day_reason(query, user_id, data.split(":", 1)[1], context)
        return
    if data.startswith("jor_report_send:"):
        await _on_report_send(query, int(data.split(":", 1)[1]), context)
        return

    jornada = get_jornada(user_id)
    status = jornada.status if jornada else "none"
    handler = _JORNADA_SOP.get_handler(status, data)
    if handler is None:
        logger.warning(
            f"[jornada] transición inválida status={status!r} trigger={data!r} user={user_id}",
        )
        await query.answer("Acción no disponible en este estado.", show_alert=True)
        return

    await handler(query, user_id, context)


# ── Step handlers ─────────────────────────────────────────────────────────────


async def _on_start(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw_today = date.today().weekday()
    today = raw_today if raw_today <= 4 else 4  # fin de semana → viernes
    is_weekend = raw_today > 4

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await query.edit_message_text("Perfil de docente no encontrado.")
            return
        periods = await get_schedule_for_day(session, teacher.id, today)

    if not periods:
        await query.edit_message_text(
            "📋 *No hay horario cargado para este día.*\n\n"
            "Usa *«Cambiar día»* para seleccionar el día que quieres registrar.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_FINISHED_KEYBOARD,
        )
        return

    period_list = _build_period_list(periods)
    start_index = len(period_list) if is_weekend else _current_period_index(period_list)

    real_today = date.today()
    if is_weekend:
        days_to_friday = (real_today.weekday() - 4) % 7
        session_date = real_today - timedelta(days=days_to_friday)
    else:
        session_date = real_today

    if start_index >= len(period_list):
        jornada = JornadaSession(
            teacher_id=teacher.id,
            chat_id=query.message.chat_id,
            day_of_week=today,
            periods=period_list,
            current_index=len(period_list) - 1,
            status="done",
            session_date=session_date,
        )
        set_jornada(user_id, jornada)
        from schoolai.bot.state import DAY_NAMES
        if is_weekend:
            msg = (
                f"📅 *Hoy es fin de semana.*\n\n"
                f"Cargué el horario del *{DAY_NAMES[today]}*.\n"
                "_Usa «Seleccionar período» para registrar o «Cambiar día» para otro día._"
            )
        else:
            msg = "✅ *Todos los períodos de hoy ya pasaron.*\n\n¿Qué deseas hacer?"
        await query.edit_message_text(
            msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_FINISHED_KEYBOARD,
        )
        return

    jornada = JornadaSession(
        teacher_id=teacher.id,
        chat_id=query.message.chat_id,
        day_of_week=today,
        periods=period_list,
        current_index=start_index,
        session_date=session_date,
    )
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    await _send_period_card(context.bot, jornada, user_id)
    logger.info(f"[jornada] started user={user_id} periods={len(period_list)}")


async def _on_here(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    jornada = get_jornada(user_id)
    if not jornada or not jornada.current_period:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    p = jornada.current_period
    jornada.status = "active"
    jornada.grade_id = p["grade_id"]
    jornada.grade_name = p["grade_name"]
    jornada.subject_id = p["subject_id"]
    jornada.subject_name = p["subject_name"]
    set_jornada(user_id, jornada)

    await query.edit_message_text(
        f"✅ *{_hora_label(p['period_num'])}  ·  {p['grade_name']} — {p['subject_name']}*\n"
        f"🕐 {p['start_time']}–{p['end_time']}\n\n"
        "_Contexto activo. Registra asistencia o tareas normalmente._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_active_keyboard(has_prev=jornada.current_index > 0),
    )
    tmp = await query.message.reply_text(".", reply_markup=REMOVE_KEYBOARD)
    await tmp.delete()
    logger.info(
        f"[jornada] active user={user_id} grade={p['grade_name']} subject={p['subject_name']}",
    )


async def _on_skip(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    jornada = get_jornada(user_id)
    if not jornada:
        return
    jornada.current_index += 1
    jornada.status = "waiting"
    jornada.clear_context()
    jornada.awaiting_other_reason = None
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    if not jornada.current_period:
        await _finish_jornada(context.bot, user_id, jornada)
        return
    await _send_period_card(context.bot, jornada, user_id)


async def _on_absent_menu(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    jornada = get_jornada(user_id)
    if not jornada or not jornada.current_period:
        return
    p = jornada.current_period
    await query.edit_message_text(
        f"🚫 *{p['grade_name']} — {p['subject_name']}*\n"
        f"🕐 {p['start_time']}–{p['end_time']}\n\n"
        "_¿Cuál es el motivo de tu ausencia?_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_ABSENT_REASON_KEYBOARD,
    )


async def _on_absent_reason(
    query, user_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    jornada = get_jornada(user_id)
    if not jornada:
        return

    if reason == "other":
        jornada.awaiting_other_reason = "period"
        set_jornada(user_id, jornada)
        await query.edit_message_text(
            "✏️ *¿Cuál es el motivo?*\n_Escribe una breve descripción:_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    p = jornada.current_period
    if p:
        reason_label = _ABSENT_REASONS.get(reason, reason)
        jornada.absences.append(
            {
                "period_num":   p["period_num"],
                "grade_name":   p["grade_name"],
                "subject_name": p["subject_name"],
                "reason":       reason,
                "reason_label": reason_label,
            },
        )
        logger.info(
            f"[jornada] ausencia docente user={user_id} "
            f"grade={p['grade_name']} reason={reason}",
        )

    jornada.current_index += 1
    jornada.status = "waiting"
    jornada.clear_context()
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    if not jornada.current_period:
        await _finish_jornada(context.bot, user_id, jornada)
        return
    await _send_period_card(context.bot, jornada, user_id)


async def _on_absent_day(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    await query.edit_message_text(
        "🔴 *Ausencia — jornada completa*\n\n_¿Cuál es el motivo?_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_ABSENT_DAY_REASON_KEYBOARD,
    )


async def _on_absent_day_reason(
    query, user_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    raw_today = date.today().weekday()
    today = raw_today if raw_today <= 4 else 4
    jornada = get_jornada(user_id)

    if jornada is None:
        async with get_db_session() as session:
            teacher = await get_teacher_by_telegram(session, user_id)
            if not teacher:
                await query.edit_message_text("Perfil de docente no encontrado.")
                return
            periods = await get_schedule_for_day(session, teacher.id, today)
        period_list = _build_period_list(periods)
        jornada = JornadaSession(
            teacher_id=teacher.id,
            chat_id=query.message.chat_id,
            day_of_week=today,
            periods=period_list,
            current_index=0,
            session_date=date.today(),
        )

    if reason == "other":
        jornada.awaiting_other_reason = "day"
        set_jornada(user_id, jornada)
        await query.edit_message_text(
            "✏️ *¿Cuál es el motivo?*\n_Escribe una breve descripción:_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    reason_label = _ABSENT_REASONS.get(reason, reason)
    _apply_day_absences(jornada, reason, reason_label)
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    logger.info(
        f"[jornada] ausencia total user={user_id} reason={reason} periods={len(jornada.periods)}",
    )
    await _finish_jornada(context.bot, user_id, jornada)


def _apply_day_absences(jornada: JornadaSession, reason: str, reason_label: str) -> None:
    jornada.absences = [
        {
            "period_num":   p["period_num"],
            "grade_name":   p["grade_name"],
            "subject_name": p["subject_name"],
            "reason":       reason,
            "reason_label": reason_label,
        }
        for p in jornada.periods
    ]
    jornada.current_index = len(jornada.periods)
    jornada.status = "done"
    jornada.awaiting_other_reason = None


async def _on_next(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    jornada = get_jornada(user_id)
    if not jornada:
        return
    jornada.current_index += 1
    jornada.status = "waiting"
    jornada.clear_context()
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    if not jornada.current_period:
        await _finish_jornada(context.bot, user_id, jornada)
        return
    await _send_period_card(context.bot, jornada, user_id)


async def _on_pause(query, user_id: int, context=None) -> None:
    jornada = get_jornada(user_id)
    if not jornada:
        return
    jornada.status = "paused"
    jornada.clear_context()
    set_jornada(user_id, jornada)
    p = jornada.current_period
    period_info = f"*{p['grade_name']} — {p['subject_name']}*" if p else "—"
    await query.edit_message_text(
        f"⏸ *Jornada pausada*\n\nPróxima clase: {period_info}\n\n"
        "_Estás en Modo Libre. Toca Retomar cuando estés listo._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("🟢 Retomar Jornada", callback_data="jor_resume"),
                InlineKeyboardButton("🔴 Finalizar",       callback_data="jor_end"),
            ]],
        ),
    )
    logger.info(f"[jornada] paused user={user_id}")


async def _on_resume(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    jornada = get_jornada(user_id)
    if not jornada:
        return
    jornada.status = "waiting"
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    await _send_period_card(context.bot, jornada, user_id)
    logger.info(f"[jornada] resumed user={user_id}")


async def _on_end(query, user_id: int, context=None) -> None:
    jornada = get_jornada(user_id)
    completed = jornada.current_index if jornada else 0

    if jornada and jornada.absences:
        try:
            from schoolai.bot.jornada.card import _save_teacher_absences
            await _save_teacher_absences(jornada)
        except Exception as exc:
            logger.error(f"[jornada:end] error guardando ausencias: {exc}")

    clear_jornada(user_id)
    await query.edit_message_text(
        f"🔴 *Modo Jornada finalizado.*\n"
        f"Clases completadas: {completed}\n\n"
        "_Toca 📅 Jornada cuando quieras retomar._",
        parse_mode=ParseMode.MARKDOWN,
    )
    await query.message.reply_text("📅 Toca Jornada para retomar.", reply_markup=JORNADA_KEYBOARD)
    logger.info(f"[jornada] ended user={user_id}")


async def _on_back(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    jornada = get_jornada(user_id)
    if not jornada or jornada.current_index == 0:
        await query.answer("Ya estás en la primera clase.", show_alert=True)
        return
    jornada.current_index -= 1
    jornada.status = "waiting"
    jornada.clear_context()
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    await _send_period_card(context.bot, jornada, user_id)
    logger.info(f"[jornada] back user={user_id} index={jornada.current_index}")


async def _on_restart(query, user_id: int, context) -> None:
    jornada = get_jornada(user_id)
    if not jornada:
        return
    jornada.current_index = 0
    jornada.status = "waiting"
    jornada.clear_context()
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    await _send_period_card(context.bot, jornada, user_id)


async def _on_pick(query, user_id: int, context=None) -> None:
    jornada = get_jornada(user_id)
    if not jornada:
        return
    buttons = [
        [
            InlineKeyboardButton(
                f"{p['period_num']}. {p['grade_name']} — {p['subject_name']}  {p['start_time']}",
                callback_data=f"jor_goto:{i}",
            ),
        ]
        for i, p in enumerate(jornada.periods)
    ]
    await query.edit_message_text(
        "📋 *Selecciona el período:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _on_goto(query, user_id: int, index: int, context) -> None:
    jornada = get_jornada(user_id)
    if not jornada or not (0 <= index < len(jornada.periods)):
        return
    jornada.current_index = index
    jornada.status = "waiting"
    jornada.clear_context()
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    await _send_period_card(context.bot, jornada, user_id)


async def _on_day_pick(query, user_id: int) -> None:
    """Muestra selector de día para registro retroactivo."""
    jornada = get_jornada(user_id)
    current_dow = jornada.day_of_week if jornada else date.today().weekday()
    await query.edit_message_text(
        "📅 *¿Para qué día quieres registrar?*\n"
        "_Se cargará el horario de ese día._",
        parse_mode="Markdown",
        reply_markup=day_pick_keyboard(current_dow),
    )


async def _on_day_select(
    query, user_id: int, dow: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Recarga la jornada para el día de semana seleccionado."""
    if not (0 <= dow <= 4):
        await query.answer("Día inválido.", show_alert=True)
        return

    # Calcular la fecha del día seleccionado (ocurrencia más reciente ≤ hoy)
    today = date.today()
    days_back = (today.weekday() - dow) % 7
    session_date = today - timedelta(days=days_back)

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await query.edit_message_text("Perfil de docente no encontrado.")
            return
        periods = await get_schedule_for_day(session, teacher.id, dow)

    if not periods:
        from schoolai.bot.state import DAY_NAMES
        await query.edit_message_text(
            f"No tienes clases registradas para ese día ({DAY_NAMES[dow]}).",
        )
        return

    period_list = _build_period_list(periods)

    jornada = get_jornada(user_id)
    if jornada is None:
        jornada = JornadaSession(
            teacher_id=teacher.id,
            chat_id=query.message.chat_id,
            day_of_week=dow,
            periods=period_list,
            session_date=session_date,
            status="done",
            current_index=len(period_list) - 1,
        )
    else:
        jornada.day_of_week = dow
        jornada.periods = period_list
        jornada.session_date = session_date
        jornada.current_index = len(period_list) - 1
        jornada.status = "done"
        jornada.clear_context()

    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)

    from schoolai.bot.state import DAY_NAMES
    await query.message.reply_text(
        f"📅 *Jornada del {DAY_NAMES[dow]} {session_date.strftime('%d/%m/%Y')}*\n"
        "_Usa «Seleccionar período» para registrar asistencia o tareas._",
        parse_mode="Markdown",
        reply_markup=_FINISHED_KEYBOARD,
    )
    logger.info(f"[jornada] day_select user={user_id} dow={dow} date={session_date}")


async def _on_report_send(query, grade_id: int, context) -> None:
    from datetime import date as _date

    from schoolai.skills.whatsapp.tutor_notify import send_report_to_representatives

    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=query.message.chat.id,
        text="⏳ Enviando a representantes...",
    )
    sent, failed = await send_report_to_representatives(grade_id, _date.today())
    lines = []
    if sent:
        lines.append(f"✅ Enviado a {sent} representante(s).")
    if failed:
        lines.append(f"❌ Falló el envío a {failed} representante(s).")
    if not sent and not failed:
        lines.append("ℹ️ No hay representantes con WhatsApp registrado para este curso.")
    await context.bot.send_message(chat_id=query.message.chat.id, text="\n".join(lines))


# ── Banner de contexto activo ─────────────────────────────────────────────────


def jornada_context_banner(user_id: int) -> str | None:
    """Retorna una línea de contexto para adjuntar a respuestas del bot."""
    s = get_jornada(user_id)
    if not s or s.status != "active":
        return None
    return f"\n\n📌 _Modo Jornada: {s.grade_name} — {s.subject_name}_"


# ── Interceptor: texto libre para "Otro motivo" ───────────────────────────────


async def _absent_other_reason_interceptor(update, user_id: int) -> bool:
    jornada = get_jornada(user_id)
    if not jornada or not jornada.awaiting_other_reason:
        return False

    mode = jornada.awaiting_other_reason
    custom_label = update.message.text.strip()
    if not custom_label:
        await update.message.reply_text(
            "✏️ Por favor escribe el motivo de tu ausencia (no puede estar vacío):",
        )
        return True

    bot = update.get_bot()

    if mode == "period":
        p = jornada.current_period
        if p:
            jornada.absences.append({
                "period_num":   p["period_num"],
                "grade_name":   p["grade_name"],
                "subject_name": p["subject_name"],
                "reason":       "other",
                "reason_label": custom_label,
            })
            logger.info(
                f"[jornada] ausencia docente user={user_id} "
                f"grade={p['grade_name']} reason=other custom={custom_label!r}",
            )
        jornada.current_index += 1
        jornada.status = "waiting"
        jornada.clear_context()
        jornada.awaiting_other_reason = None
        set_jornada(user_id, jornada)
        await update.message.reply_text("✅ Motivo registrado.")
        if not jornada.current_period:
            await _finish_jornada(bot, user_id, jornada)
        else:
            await _send_period_card(bot, jornada, user_id)
    else:  # "day"
        _apply_day_absences(jornada, "other", custom_label)
        set_jornada(user_id, jornada)
        logger.info(
            f"[jornada] ausencia total user={user_id} reason=other custom={custom_label!r} "
            f"periods={len(jornada.periods)}",
        )
        await update.message.reply_text("✅ Motivo registrado.")
        await _finish_jornada(bot, user_id, jornada)

    return True


# Auto-registro al importar
from schoolai.bot.text_interceptors import text_interceptors  # noqa: E402

text_interceptors.register(priority=5, name="jornada_absent_other")(_absent_other_reason_interceptor)
