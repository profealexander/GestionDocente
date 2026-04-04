"""Modo Jornada — flujo secuencial por horario del docente.

Estados:
  waiting → docente confirmó inicio, esperando llegar al aula
  active  → en clase, contexto grade+subject activo
  paused  → receso o pausa manual
  done    → todos los períodos completados

Callbacks:
  jor_start    — iniciar modo jornada
  jor_here     — "Estoy en clase" (activa contexto)
  jor_skip     — saltar período actual
  jor_next     — avanzar al siguiente período
  jor_pause    — pausar jornada
  jor_resume   — retomar jornada
  jor_end      — finalizar jornada manualmente
"""

import asyncio
import re
from datetime import date, datetime, timedelta
from datetime import time as _time
from functools import cache

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.handlers import JORNADA_KEYBOARD, REMOVE_KEYBOARD
from schoolai.bot.sop import SOPEngine
from schoolai.bot.state import (
    DAY_NAMES,
    JornadaSession,
    clear_jornada,
    get_jornada,
    iter_all_jornada,
    set_jornada,
)
from schoolai.db.connection import async_session
from schoolai.db.models.teacher import Teacher
from schoolai.skills.db.schedule_service import get_schedule_for_day, get_teacher_by_telegram

# ── Teclados estáticos cacheados ──────────────────────────────────────────────

_ABSENT_REASONS: dict[str, str] = {
    "meeting":  "📋 Reunión delegada",
    "permit":   "📝 Permiso",
    "sick":     "🤒 Enfermedad / Malestar",
    "other":    "❓ Otro motivo",
}

_ABSENT_REASON_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("📋 Reunión delegada", callback_data="jor_absent_reason:meeting"),
            InlineKeyboardButton("📝 Permiso",          callback_data="jor_absent_reason:permit"),
        ],
        [
            InlineKeyboardButton("🤒 Enfermedad",       callback_data="jor_absent_reason:sick"),
            InlineKeyboardButton("❓ Otro motivo",      callback_data="jor_absent_reason:other"),
        ],
    ],
)

def _active_keyboard(has_prev: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("▶️ Siguiente clase", callback_data="jor_next"),
            InlineKeyboardButton("⏸ Pausar",           callback_data="jor_pause"),
        ],
    ]
    if has_prev:
        rows.append([InlineKeyboardButton("⬅️ Clase anterior", callback_data="jor_back")])
    return InlineKeyboardMarkup(rows)

_FINISHED_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("🔄 Recorrer desde el inicio", callback_data="jor_restart"),
            InlineKeyboardButton("📋 Seleccionar período", callback_data="jor_pick"),
        ],
    ],
)

# ── SOP transition table ───────────────────────────────────────────────────────
# Built lazily (after all _on_* functions are defined) via _build_sop().
_JORNADA_SOP: SOPEngine | None = None


def _build_sop() -> SOPEngine:
    return SOPEngine(
        {
            # jor_start — arranca desde cualquier estado
            ("*", "jor_start"): _on_start,
            # waiting — tarjeta de período mostrada, esperando al docente
            ("waiting", "jor_here"): _on_here,
            ("waiting", "jor_skip"): _on_skip,
            ("waiting", "jor_back"): _on_back,
            ("waiting", "jor_absent"): _on_absent_menu,
            ("waiting", "jor_pause"): _on_pause,
            ("waiting", "jor_end"): _on_end,
            # active — docente en clase
            ("active", "jor_next"): _on_next,
            ("active", "jor_back"): _on_back,
            ("active", "jor_pause"): _on_pause,
            ("active", "jor_end"): _on_end,
            # paused — en receso
            ("paused", "jor_resume"): _on_resume,
            ("paused", "jor_end"): _on_end,
            # done — todos los períodos terminados
            ("done", "jor_restart"): _on_restart,
            ("done", "jor_pick"): _on_pick,
            # navegación libre (cualquier estado)
            ("*", "jor_restart"): _on_restart,
            ("*", "jor_pick"): _on_pick,
            # jor_goto:{i} se parsea por separado en el dispatcher
        },
    )


# ── Job de reconexión — corre 20s después del arranque ───────────────────────


async def job_reconnect_resume(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detecta sesiones de jornada activas cuyo período ya pasó y ofrece retomar.

    Se ejecuta una única vez, 20 s después del arranque (tiempo para procesar
    los mensajes que estaban en cola durante la desconexión).
    """
    sessions = iter_all_jornada()
    if not sessions:
        return

    for user_id, jornada in sessions:
        if jornada.status == "done":
            continue
        if not jornada.periods:
            continue

        correct_index = _current_period_index(jornada.periods)

        # Sesión al día o ya llegamos al último período → no tocar
        if correct_index <= jornada.current_index:
            continue

        # Avanzar al período que corresponde ahora
        jornada.current_index = min(correct_index, len(jornada.periods) - 1)
        jornada.status = "waiting"
        jornada.clear_context()
        set_jornada(user_id, jornada)

        p = jornada.current_period
        if not p:
            continue

        now_str = datetime.now().strftime("%H:%M")
        try:
            await context.bot.send_message(
                chat_id=jornada.chat_id,
                text=(
                    f"📶 *Reconectado — {now_str}*\n\n"
                    f"Según la hora actual corresponde:\n\n"
                    f"*{_hora_label(p['period_num'])}  ·  {p['grade_name']}  —  {p['subject_name']}*\n"
                    f"🕐 {p['start_time']} – {p['end_time']}\n\n"
                    f"_¿Estás en esta clase?_"
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✅ Sí, estoy aquí", callback_data="jor_here"),
                            InlineKeyboardButton("🚫 No asistí",      callback_data="jor_absent"),
                        ],
                        [
                            InlineKeyboardButton("📋 Seleccionar período", callback_data="jor_pick"),
                        ],
                    ],
                ),
            )
            logger.info(
                f"[jornada:reconnect] prompted user={user_id} "
                f"period={p['period_num']} grade={p['grade_name']}",
            )
        except Exception as e:
            logger.warning(f"[jornada:reconnect] no se pudo notificar user={user_id}: {e}")


# ── Job 06:00 ─────────────────────────────────────────────────────────────────


async def job_morning_notify(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía invitación a Modo Jornada a todos los docentes con horario hoy."""
    today = date.today().weekday()  # 0=Lunes … 4=Viernes
    if today > 4:
        return  # fin de semana

    async with async_session() as session:
        teachers = (
            (
                await session.execute(
                    select(Teacher).where(
                        Teacher.is_active.is_(True), Teacher.telegram_id.isnot(None),
                    ),
                )
            )
            .scalars()
            .all()
        )

        # Pre-load schedules para todos los docentes en paralelo
        schedules = await asyncio.gather(
            *[get_schedule_for_day(session, teacher.id, today) for teacher in teachers],
        )
        teacher_periods = list(zip(teachers, schedules))

    _start_btn = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🟢 Iniciar Modo Jornada", callback_data="jor_start"),
            ],
        ],
    )

    async def _notify(teacher, periods) -> None:
        if not periods:
            return
        first = periods[0]
        try:
            await context.bot.send_message(
                chat_id=teacher.telegram_id,
                text=(
                    f"📅 *Buenos días — {DAY_NAMES[today]}*\n\n"
                    f"Tienes *{len(periods)} clase(s)* hoy.\n"
                    f"Primera: *{first.grade.name} — {first.subject.name}*  "
                    f"{first.start_time}–{first.end_time}"
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_start_btn,
            )
            logger.info(
                f"[jornada] morning notify → teacher={teacher.id} telegram={teacher.telegram_id}",
            )
        except Exception as e:
            logger.warning(f"[jornada] could not notify teacher={teacher.id}: {e}")

    await asyncio.gather(*[_notify(t, p) for t, p in teacher_periods])


# ── Comando /jornada ───────────────────────────────────────────────────────────


async def handle_jornada_command(update, context) -> None:
    """Permite iniciar Modo Jornada manualmente en cualquier momento."""
    user_id = update.effective_user.id
    session_obj = get_jornada(user_id)

    if session_obj and session_obj.status != "done":
        await _send_period_card(context.bot, session_obj, user_id)
        return

    today = date.today().weekday()
    if today > 4:
        await update.message.reply_text("Hoy es fin de semana. ¡Descansa! 😄")
        return

    async with async_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await update.message.reply_text(
                "No tienes un perfil de docente vinculado.\n"
                "Usa /db → 📅 Horario para configurarlo.",
            )
            return

        periods = await get_schedule_for_day(session, teacher.id, today)

    if not periods:
        await update.message.reply_text(
            f"No tienes clases registradas para hoy ({DAY_NAMES[today]}).\n"
            "Usa /db → 📅 Horario para registrar tu horario.",
        )
        return

    period_list = _build_period_list(periods)
    start_index = _current_period_index(period_list)

    if start_index >= len(period_list):
        await update.message.reply_text(
            "✅ *Todos los períodos de hoy ya pasaron.*\n\n¿Qué deseas hacer?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_FINISHED_KEYBOARD,
        )
        # Guardamos la sesión completa para poder navegar desde los botones
        jornada = JornadaSession(
            teacher_id=teacher.id,
            chat_id=update.message.chat_id,
            day_of_week=today,
            periods=period_list,
            current_index=len(period_list) - 1,
            status="done",
        )
        set_jornada(user_id, jornada)
        return

    jornada = JornadaSession(
        teacher_id=teacher.id,
        chat_id=update.message.chat_id,
        day_of_week=today,
        periods=period_list,
        current_index=start_index,
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

    # Weekend gate: bloquear jor_start en fin de semana
    if data == "jor_start" and date.today().weekday() > 4:
        await query.answer("Hoy es fin de semana. ¡Descansa! 😄", show_alert=True)
        return

    # jor_goto:{i} — tratamiento especial por el argumento numérico
    if data.startswith("jor_goto:"):
        await _on_goto(query, user_id, int(data.split(":")[1]), context)
        return

    # jor_absent_reason:{reason} — confirmación de razón de ausencia
    if data.startswith("jor_absent_reason:"):
        reason = data.split(":", 1)[1]
        await _on_absent_reason(query, user_id, reason, context)
        return

    # jor_report_send:{grade_id} — enviar reporte al representante
    if data.startswith("jor_report_send:"):
        grade_id = int(data.split(":", 1)[1])
        await _on_report_send(query, grade_id, context)
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
    today = date.today().weekday()

    async with async_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await query.edit_message_text("Perfil de docente no encontrado.")
            return
        periods = await get_schedule_for_day(session, teacher.id, today)

    if not periods:
        await query.edit_message_text("No hay clases registradas para hoy.")
        return

    period_list = _build_period_list(periods)
    start_index = _current_period_index(period_list)

    if start_index >= len(period_list):
        jornada = JornadaSession(
            teacher_id=teacher.id,
            chat_id=query.message.chat_id,
            day_of_week=today,
            periods=period_list,
            current_index=len(period_list) - 1,
            status="done",
        )
        set_jornada(user_id, jornada)
        await query.edit_message_text(
            "✅ *Todos los períodos de hoy ya pasaron.*\n\n¿Qué deseas hacer?",
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
    set_jornada(user_id, jornada)

    await query.edit_message_reply_markup(reply_markup=None)

    if not jornada.current_period:
        await _finish_jornada(context.bot, user_id, jornada)
        return

    await _send_period_card(context.bot, jornada, user_id)


async def _on_absent_menu(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el sub-menú de razones de ausencia del docente."""
    jornada = get_jornada(user_id)
    if not jornada or not jornada.current_period:
        return

    p = jornada.current_period
    await query.edit_message_text(
        f"🚫 *{p['grade_name']} — {p['subject_name']}*\n"
        f"🕐 {p['start_time']}–{p['end_time']}\n\n"
        "_¿Cuál es el motivo de tu ausencia?_",
        parse_mode="Markdown",
        reply_markup=_ABSENT_REASON_KEYBOARD,
    )


async def _on_absent_reason(
    query, user_id: int, reason: str, context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Registra la ausencia del docente con razón y avanza al siguiente período."""
    jornada = get_jornada(user_id)
    if not jornada:
        return

    p = jornada.current_period
    if p:
        reason_label = _ABSENT_REASONS.get(reason, "Otro motivo")
        jornada.absences.append(
            {
                "period_num": p["period_num"],
                "grade_name": p["grade_name"],
                "subject_name": p["subject_name"],
                "reason": reason,
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
        f"⏸ *Jornada pausada*\n\n"
        f"Próxima clase: {period_info}\n\n"
        "_Estás en Modo Libre. Toca Retomar cuando estés listo._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🟢 Retomar Jornada", callback_data="jor_resume"),
                    InlineKeyboardButton("🔴 Finalizar", callback_data="jor_end"),
                ],
            ],
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
    clear_jornada(user_id)
    await query.edit_message_text(
        f"🔴 *Modo Jornada finalizado.*\n"
        f"Clases completadas: {completed}\n\n"
        "_Toca 📅 Jornada cuando quieras retomar._",
        parse_mode=ParseMode.MARKDOWN,
    )
    await query.message.reply_text("📅 Toca Jornada para retomar.", reply_markup=JORNADA_KEYBOARD)
    logger.info(f"[jornada] ended user={user_id}")


# ── Helpers ───────────────────────────────────────────────────────────────────


@cache
def _parse_time(s: str) -> _time:
    """Convierte 'HH:MM' a time object. Cacheado porque los horarios no cambian."""
    h, m = s.split(":")
    return _time(int(h), int(m))


def _current_period_index(periods: list[dict]) -> int:
    """Retorna el índice del período activo o próximo según la hora actual.
    - Si la hora está dentro de un período → ese índice
    - Si está entre períodos → el siguiente
    - Si ya pasaron todos → len(periods)
    - Si no ha empezado ninguno → 0
    """
    now = datetime.now().time()

    for i, p in enumerate(periods):
        start = _parse_time(p["start_time"])
        end = _parse_time(p["end_time"])
        if start <= now <= end:
            return i  # dentro del período
        if now < start:
            return i  # antes de que empiece este período

    return len(periods)  # todos pasaron


_ORDINAL = {1:"1RA",2:"2DA",3:"3RA",4:"4TA",5:"5TA",6:"6TA",7:"7MA",8:"8VA"}


def _hora_label(n: int) -> str:
    return f"{_ORDINAL.get(n, f'{n}RA')} HORA"


def _build_period_list(periods) -> list[dict]:
    return [
        {
            "period_num": p.period_num,
            "start_time": p.start_time,
            "end_time": p.end_time,
            "grade_id": p.grade_id,
            "grade_name": p.grade.name,
            "subject_id": p.subject_id,
            "subject_name": p.subject.name,
        }
        for p in periods
    ]


async def _send_period_card(bot, jornada: JornadaSession, user_id: int) -> None:
    p = jornada.current_period
    total = len(jornada.periods)
    num = jornada.current_index + 1

    text = (
        f"📚 *Clase {num} de {total}  ·  {_hora_label(p['period_num'])}*\n\n"
        f"*{p['grade_name']}  —  {p['subject_name']}*\n"
        f"🕐 {p['start_time']} – {p['end_time']}\n\n"
        "_¿Ya estás en el aula?_"
    )
    buttons = [
        [
            InlineKeyboardButton("✅ Estoy en clase", callback_data="jor_here"),
            InlineKeyboardButton("🚫 No asistí",      callback_data="jor_absent"),
        ],
        [
            InlineKeyboardButton("⏭ Saltar",          callback_data="jor_skip"),
            InlineKeyboardButton("⏸ Pausar Jornada",  callback_data="jor_pause"),
        ],
    ]
    if jornada.current_index > 0:
        buttons.append([InlineKeyboardButton("⬅️ Clase anterior", callback_data="jor_back")])
    buttons.append([InlineKeyboardButton("🔴 Finalizar Jornada", callback_data="jor_end")])

    await bot.send_message(
        chat_id=jornada.chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _finish_jornada(bot, user_id: int, jornada: JornadaSession) -> None:
    total = len(jornada.periods)
    absences = jornada.absences

    lines = [f"🎉 *¡Jornada completada!*\nClases del día: *{total}*"]

    if absences:
        lines.append(f"\n⚠️ *Ausencias registradas ({len(absences)}):*")
        for a in absences:
            lines.append(
                f"  • P{a['period_num']} {a['grade_name']} — {a['subject_name']}"
                f"\n    _{a['reason_label']}_",
            )
    else:
        lines.append("\n_Buen trabajo. Hasta mañana._")

    clear_jornada(user_id)
    await bot.send_message(
        chat_id=jornada.chat_id,
        text="\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=JORNADA_KEYBOARD,
    )
    logger.info(f"[jornada] completed user={user_id} total={total} absences={len(absences)}")

    # Generar reportes por curso y mostrar en Telegram con botón de aprobación
    try:
        from datetime import date as _date
        from telegram import InlineKeyboardButton as _Btn, InlineKeyboardMarkup as _Kbd
        from schoolai.skills.whatsapp.tutor_notify import build_daily_reports, format_telegram_report

        today = _date.today()
        reports = await build_daily_reports(today)

        if reports:
            await bot.send_message(
                chat_id=jornada.chat_id,
                text="📋 <b>Reportes de jornada listos</b> — revisa y aprueba el envío:",
                parse_mode=ParseMode.HTML,
            )
            for report in reports:
                text = format_telegram_report(report, today)
                keyboard = _Kbd([[
                    _Btn(
                        "📤 Notificar a todos los representantes",
                        callback_data=f"jor_report_send:{report.grade_id}",
                    ),
                ]])
                await bot.send_message(
                    chat_id=jornada.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
    except Exception as exc:
        logger.error(f"[jornada] error generando reportes: {exc}")


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
    """Reinicia la jornada desde el período 1."""
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
    """Muestra la lista de todos los períodos para seleccionar uno."""
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
    """Salta directamente al período seleccionado."""
    jornada = get_jornada(user_id)
    if not jornada or not (0 <= index < len(jornada.periods)):
        return
    jornada.current_index = index
    jornada.status = "waiting"
    jornada.clear_context()
    set_jornada(user_id, jornada)
    await query.edit_message_reply_markup(reply_markup=None)
    await _send_period_card(context.bot, jornada, user_id)


# ── Banner de contexto activo (para appender en respuestas) ───────────────────


def jornada_context_banner(user_id: int) -> str | None:
    """Retorna una línea de contexto para adjuntar a respuestas del bot."""
    s = get_jornada(user_id)
    if not s or s.status != "active":
        return None
    return f"\n\n📌 _Modo Jornada: {s.grade_name} — {s.subject_name}_  [▶️ Siguiente](jor_next)"


# ── /horario ──────────────────────────────────────────────────────────────────

# Tiempos estándar por número de hora (bachillerato, 8 horas)
_PERIOD_TIMES: dict[int, tuple[str, str]] = {
    1: ("07:30", "08:15"),
    2: ("08:15", "09:00"),
    3: ("09:00", "09:45"),
    4: ("09:45", "10:30"),
    5: ("10:50", "11:30"),
    6: ("11:30", "12:10"),
    7: ("12:10", "12:50"),
    8: ("12:50", "13:30"),
}
_TOTAL_PERIODS = 8


_ORDINAL_TO_NUM = {
    "PRIMERO": "1", "PRIMERA": "1", "SEGUNDO": "2", "SEGUNDA": "2",
    "TERCERO": "3", "TERCERA": "3", "CUARTO": "4", "CUARTA": "4",
    "QUINTO": "5", "SEXTO": "6", "SEPTIMO": "7", "SÉPTIMO": "7",
    "OCTAVO": "8", "NOVENO": "9", "DECIMO": "10", "DÉCIMO": "10",
    "INICIAL": "I", "PREPARATORIA": "P",
}
_STOP_WORDS = {"y", "de", "del", "la", "el", "los", "las", "con", "en", "a", "e", "o"}
# Receso entre H4 y H5
_BREAK_BEFORE = 5


def _grade_abbrev(name: str) -> str:
    """'PRIMERO BT' → '1BT', 'OCTAVO EGB' → '8EGB'"""
    parts = name.upper().split()
    num = _ORDINAL_TO_NUM.get(parts[0], parts[0])
    level = parts[-1] if len(parts) > 1 else ""
    return f"{num}{level}" if level in ("BT", "EGB") else num


def _subject_abbrev(name: str) -> str:
    """'Contabilidad General' → 'CG', 'Gestión Contable y Adm. Financiera' → 'GCAF'"""
    words = [w for w in name.split() if w.lower() not in _STOP_WORDS and len(w) > 2]
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0].upper() for w in words)


def _build_schedule_text(periods: list, day: int) -> str:
    by_num = {p.period_num: p for p in periods}
    day_name = DAY_NAMES[day].upper()
    lines = [f"📅 *{day_name}*", ""]
    for h in range(1, _TOTAL_PERIODS + 1):
        if h == _BREAK_BEFORE:
            lines.append("")
        start = _PERIOD_TIMES.get(h, ("—:—", "—:—"))[0]
        ord_label = _ORDINAL.get(h, str(h))
        if h in by_num:
            p = by_num[h]
            grade = _grade_abbrev(p.grade.name)
            subj = _subject_abbrev(p.subject.name)
            lines.append(f"`{ord_label}` {start}  {grade} · {subj}")
        else:
            lines.append(f"`{ord_label}` {start}  —")
    return "\n".join(lines)


def _day_nav_keyboard(current_day: int) -> InlineKeyboardMarkup:
    labels = ["LUN", "MAR", "MIÉ", "JUE", "VIE"]
    buttons = [
        InlineKeyboardButton(
            f"·{labels[d]}·" if d == current_day else labels[d],
            callback_data=f"hor_day:{d}",
        )
        for d in range(5)
    ]
    return InlineKeyboardMarkup([buttons])


async def handle_horario_command(update, context) -> None:
    user_id = update.effective_user.id
    today = date.today().weekday()
    if today > 4:
        today = 0  # fin de semana → mostrar lunes

    async with async_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await update.message.reply_text(
                "No tienes un perfil de docente vinculado.\n"
                "Usa /db → 📅 Horario para configurarlo.",
            )
            return
        periods = await get_schedule_for_day(session, teacher.id, today)

    await update.message.reply_text(
        _build_schedule_text(periods, today),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_day_nav_keyboard(today),
    )


async def handle_horario_callback(update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    day = int(query.data.split(":")[1])

    async with async_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await query.edit_message_text("Perfil de docente no encontrado.")
            return
        periods = await get_schedule_for_day(session, teacher.id, day)

    await query.edit_message_text(
        _build_schedule_text(periods, day),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_day_nav_keyboard(day),
    )


# ── Detección por lenguaje natural ────────────────────────────────────────────

_HORARIO_RE = re.compile(
    r"\b(horario|mi horario|ver horario|clases?(?: de)?(?: hoy| ma[nñ]ana)?|"
    r"qu[eé] tengo(?: hoy| ma[nñ]ana)?|"
    r"qu[eé] clases?(?: tengo)?)\b",
    re.IGNORECASE,
)

_DAY_WORDS: dict[str, int] = {
    "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
    "jueves": 3, "viernes": 4,
    "hoy": -1, "mañana": -2, "manana": -2,
}


def _extract_day_from_text(text: str) -> int:
    """Intenta extraer el día de semana del texto. Retorna -1 = hoy por defecto."""
    t = text.lower()
    for word, val in _DAY_WORDS.items():
        if word in t:
            if val == -1:
                return date.today().weekday()
            if val == -2:
                return (date.today() + timedelta(days=1)).weekday() % 5
            return val
    return date.today().weekday()


async def _horario_interceptor(update, user_id: int) -> bool:
    """Detecta solicitudes de horario en lenguaje natural."""
    text = update.message.text
    if not _HORARIO_RE.search(text):
        return False

    day = _extract_day_from_text(text)
    if day > 4:
        day = 0  # fin de semana → lunes

    async with async_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            return False
        periods = await get_schedule_for_day(session, teacher.id, day)

    await update.message.reply_text(
        _build_schedule_text(periods, day),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_day_nav_keyboard(day),
    )
    return True


async def _on_report_send(query, grade_id: int, context) -> None:
    """Envía el reporte de jornada a los representantes del curso."""
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
    await context.bot.send_message(
        chat_id=query.message.chat.id,
        text="\n".join(lines),
    )


# Auto-registro al importar este módulo (aplica a bots Libre y Jornada)
from schoolai.bot.text_interceptors import text_interceptors  # noqa: E402

text_interceptors.register(priority=8, name="horario_natural")(_horario_interceptor)
