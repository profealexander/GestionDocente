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
from datetime import date, datetime, time as _time
from functools import cache

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from schoolai.bot.handlers import JORNADA_KEYBOARD, REMOVE_KEYBOARD

from schoolai.bot.state import (
    DAY_NAMES,
    JornadaSession,
    clear_jornada,
    get_jornada,
    set_jornada,
)
from schoolai.db.connection import async_session
from schoolai.db.models.teacher import Teacher
from schoolai.skills.db.schedule_service import get_schedule_for_day, get_teacher_by_telegram


# ── Teclados estáticos cacheados ──────────────────────────────────────────────

_ACTIVE_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("▶️ Siguiente clase", callback_data="jor_next"),
    InlineKeyboardButton("⏸ Pausar",           callback_data="jor_pause"),
]])

_FINISHED_KEYBOARD = InlineKeyboardMarkup([[
    InlineKeyboardButton("🔄 Recorrer desde el inicio", callback_data="jor_restart"),
    InlineKeyboardButton("📋 Seleccionar período",      callback_data="jor_pick"),
]])


# ── Job 06:00 ─────────────────────────────────────────────────────────────────

async def job_morning_notify(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía invitación a Modo Jornada a todos los docentes con horario hoy."""
    today = date.today().weekday()  # 0=Lunes … 4=Viernes
    if today > 4:
        return  # fin de semana

    async with async_session() as session:
        teachers = (
            await session.execute(
                select(Teacher).where(Teacher.is_active.is_(True), Teacher.telegram_id.isnot(None))
            )
        ).scalars().all()

        # Pre-load schedules para todos los docentes
        teacher_periods = [
            (teacher, await get_schedule_for_day(session, teacher.id, today))
            for teacher in teachers
        ]

    _start_btn = InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Iniciar Modo Jornada", callback_data="jor_start"),
    ]])

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
            logger.info(f"[jornada] morning notify → teacher={teacher.id} telegram={teacher.telegram_id}")
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

    async with async_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await update.message.reply_text(
                "No tienes un perfil de docente vinculado.\n"
                "Usa /db → 📅 Horario para configurarlo."
            )
            return

        periods = await get_schedule_for_day(session, teacher.id, today)

    if not periods:
        await update.message.reply_text(
            f"No tienes clases registradas para hoy ({DAY_NAMES[today]}).\n"
            "Usa /db → 📅 Horario para registrar tu horario."
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
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data == "jor_start":
        await _on_start(query, user_id, context)
    elif data == "jor_here":
        await _on_here(query, user_id, context)
    elif data == "jor_skip":
        await _on_skip(query, user_id, context)
    elif data == "jor_next":
        await _on_next(query, user_id, context)
    elif data == "jor_pause":
        await _on_pause(query, user_id)
    elif data == "jor_resume":
        await _on_resume(query, user_id, context)
    elif data == "jor_end":
        await _on_end(query, user_id)
    elif data == "jor_restart":
        await _on_restart(query, user_id, context)
    elif data == "jor_pick":
        await _on_pick(query, user_id)
    elif data.startswith("jor_goto:"):
        await _on_goto(query, user_id, int(data.split(":")[1]), context)


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
        f"✅ *{p['grade_name']} — {p['subject_name']}*\n"
        f"🕐 {p['start_time']}–{p['end_time']}\n\n"
        "_Contexto activo. Registra asistencia o tareas normalmente._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_ACTIVE_KEYBOARD,
    )
    await query.message.reply_text("\u200b", reply_markup=REMOVE_KEYBOARD)
    logger.info(f"[jornada] active user={user_id} grade={p['grade_name']} subject={p['subject_name']}")


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


async def _on_pause(query, user_id: int) -> None:
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
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🟢 Retomar Jornada", callback_data="jor_resume"),
            InlineKeyboardButton("🔴 Finalizar",       callback_data="jor_end"),
        ]]),
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


async def _on_end(query, user_id: int) -> None:
    jornada = get_jornada(user_id)
    completed = jornada.current_index if jornada else 0
    clear_jornada(user_id)
    await query.edit_message_text(
        f"🔴 *Modo Jornada finalizado.*\n"
        f"Clases completadas: {completed}\n\n"
        "_Toca 📅 Jornada cuando quieras retomar._",
        parse_mode=ParseMode.MARKDOWN,
    )
    await query.message.reply_text("\u200b", reply_markup=JORNADA_KEYBOARD)
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
        end   = _parse_time(p["end_time"])
        if start <= now <= end:
            return i           # dentro del período
        if now < start:
            return i           # antes de que empiece este período

    return len(periods)        # todos pasaron


def _build_period_list(periods) -> list[dict]:
    return [
        {
            "period_num":   p.period_num,
            "start_time":   p.start_time,
            "end_time":     p.end_time,
            "grade_id":     p.grade_id,
            "grade_name":   p.grade.name,
            "subject_id":   p.subject_id,
            "subject_name": p.subject.name,
        }
        for p in periods
    ]


async def _send_period_card(bot, jornada: JornadaSession, user_id: int) -> None:
    p = jornada.current_period
    total = len(jornada.periods)
    num = jornada.current_index + 1

    text = (
        f"📚 *Clase {num} de {total}*\n\n"
        f"*{p['grade_name']}  —  {p['subject_name']}*\n"
        f"🕐 {p['start_time']} – {p['end_time']}\n\n"
        "_¿Ya estás en el aula?_"
    )
    buttons = [
        [
            InlineKeyboardButton("✅ Estoy en clase", callback_data="jor_here"),
            InlineKeyboardButton("⏭ Saltar",          callback_data="jor_skip"),
        ],
        [
            InlineKeyboardButton("⏸ Pausar Jornada",    callback_data="jor_pause"),
            InlineKeyboardButton("🔴 Finalizar Jornada", callback_data="jor_end"),
        ],
    ]

    await bot.send_message(
        chat_id=jornada.chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _finish_jornada(bot, user_id: int, jornada: JornadaSession) -> None:
    total = len(jornada.periods)
    clear_jornada(user_id)
    await bot.send_message(
        chat_id=jornada.chat_id,
        text=(
            f"🎉 *¡Jornada completada!*\n"
            f"Clases del día: *{total}*\n\n"
            "_Buen trabajo. Hasta mañana._"
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=JORNADA_KEYBOARD,
    )
    logger.info(f"[jornada] completed user={user_id} total={total}")


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


async def _on_pick(query, user_id: int) -> None:
    """Muestra la lista de todos los períodos para seleccionar uno."""
    jornada = get_jornada(user_id)
    if not jornada:
        return
    buttons = [
        [InlineKeyboardButton(
            f"{p['period_num']}. {p['grade_name']} — {p['subject_name']}  {p['start_time']}",
            callback_data=f"jor_goto:{i}",
        )]
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
    return (
        f"\n\n📌 _Modo Jornada: {s.grade_name} — {s.subject_name}_  "
        f"[▶️ Siguiente](jor_next)"
    )
