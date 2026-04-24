"""Jobs de cron del Modo Jornada — notificación matutina y reconexión."""

import asyncio
from datetime import datetime

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.state import DAY_NAMES, iter_all_jornada, set_jornada
from schoolai.db.connection import get_db_session
from schoolai.db.models.teacher import Teacher
from schoolai.skills.db.schedule_service import get_schedule_for_day
from schoolai.bot.jornada.helpers import _current_period_index, _hora_label
from schoolai.bot.jornada.keyboards import _MORNING_KEYBOARD


async def job_reconnect_resume(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detecta sesiones activas cuyo período ya pasó y ofrece retomar.

    Se ejecuta una única vez, 20 s después del arranque (tiempo para procesar
    los mensajes en cola durante la desconexión).
    """
    sessions = iter_all_jornada()
    if not sessions:
        return

    for user_id, jornada in sessions:
        if jornada.status == "done" or not jornada.periods:
            continue

        correct_index = _current_period_index(jornada.periods)
        if correct_index <= jornada.current_index:
            continue

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


async def job_morning_notify(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía invitación a Modo Jornada a todos los docentes con horario hoy."""
    from datetime import date

    today = date.today().weekday()
    if today > 4:
        return  # fin de semana

    async with get_db_session() as session:
        teachers = (
            (
                await session.execute(
                    select(Teacher).where(
                        Teacher.is_active.is_(True),
                        Teacher.telegram_id.isnot(None),
                    ),
                )
            )
            .scalars()
            .all()
        )
        schedules = await asyncio.gather(
            *[get_schedule_for_day(session, teacher.id, today) for teacher in teachers],
        )
        teacher_periods = list(zip(teachers, schedules))

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
                reply_markup=_MORNING_KEYBOARD,
            )
            logger.info(
                f"[jornada] morning notify → teacher={teacher.id} telegram={teacher.telegram_id}",
            )
        except Exception as e:
            logger.warning(f"[jornada] could not notify teacher={teacher.id}: {e}")

    _BATCH = 25
    pairs = list(teacher_periods)
    for i in range(0, len(pairs), _BATCH):
        batch = pairs[i : i + _BATCH]
        await asyncio.gather(*[_notify(t, p) for t, p in batch])
        if i + _BATCH < len(pairs):
            await asyncio.sleep(1)
