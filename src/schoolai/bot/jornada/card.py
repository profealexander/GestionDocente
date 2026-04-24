"""Tarjeta de período y pantalla de fin de jornada."""

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.bot.handlers import JORNADA_KEYBOARD
from schoolai.bot.state import JornadaSession, clear_jornada
from schoolai.bot.jornada.helpers import _hora_label


async def _save_teacher_absences(jornada: JornadaSession) -> None:
    from schoolai.skills.attendance.teacher_absence import save_teacher_absences

    await save_teacher_absences(jornada)
    logger.info(
        f"[jornada] {len(jornada.absences)} ausencias docente guardadas "
        f"teacher={jornada.teacher_id}",
    )


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
    buttons.append([
        InlineKeyboardButton("🔴 No asistiré hoy", callback_data="jor_absent_day"),
        InlineKeyboardButton("⏹ Finalizar",        callback_data="jor_end"),
    ])

    await bot.send_message(
        chat_id=jornada.chat_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _finish_jornada(bot, user_id: int, jornada: JornadaSession) -> None:
    from datetime import date as _date

    from telegram import InlineKeyboardButton as _Btn, InlineKeyboardMarkup as _Kbd

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

    saved_absences = False
    try:
        await _save_teacher_absences(jornada)
        saved_absences = True
    except Exception as exc:
        logger.error(f"[jornada] error guardando ausencias docente en BD: {exc}")

    if not saved_absences and absences:
        lines.append("\n⚠️ _Las ausencias no pudieron guardarse. Contacta al administrador._")

    clear_jornada(user_id)
    await bot.send_message(
        chat_id=jornada.chat_id,
        text="\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=JORNADA_KEYBOARD,
    )
    logger.info(f"[jornada] completed user={user_id} total={total} absences={len(absences)}")

    # Reportes por curso con botón de aprobación de envío
    try:
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

    # Notificar al inspector si el docente-tutor tuvo ausencias
    if jornada.absences:
        try:
            from schoolai.skills.whatsapp.tutor_notify import notify_inspector_tutor_absent

            reason_labels = list({a["reason_label"] for a in jornada.absences})
            reason_label = reason_labels[0] if reason_labels else "Ausencia"
            await notify_inspector_tutor_absent(
                bot,
                jornada.teacher_id,
                reason_label,
                _date.today(),
            )
        except Exception as exc:
            logger.error(f"[jornada] error notificando inspector: {exc}")
