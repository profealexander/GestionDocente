"""Handler de registro de pagos."""

from __future__ import annotations

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.bot.state import pop_pending_pago, set_pending_pago
from schoolai.db.connection import async_session
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.cuotas._helpers import _get_teacher_id
from schoolai.skills.cuotas.extractor import CuotaExtract
from schoolai.skills.cuotas.service import (
    get_activities,
    get_activity_by_name,
    register_payment,
)


def _actividad_pago_keyboard(actividades) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"💰 {a.nombre} (${a.monto:.0f})", callback_data=f"cuota_pago:{a.id}",
                ),
            ]
            for a in actividades
        ],
    )


async def _resolve_names(session, nombres: list[str], course: str | None):
    """Resuelve nombres a student_ids buscando en curso o en todos los grados."""
    extracted = [{"name": n, "status": "absent"} for n in nombres]

    if course:
        from schoolai.skills.homework.repository import find_grade

        grade = await find_grade(session, course)
        grade_id = grade.id if grade else None
        if grade_id:
            return await match_names(extracted, grade_id, session)

    # Sin curso — buscar en todos los grados, primer match gana
    from sqlalchemy import select

    from schoolai.db.models.grade import Grade

    grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()

    for g in grades:
        results = await match_names(extracted, g.id, session)
        if any(r.resolved for r in results):
            return results

    return await match_names(extracted, grades[0].id if grades else 0, session)


async def _send_pago_result(
    update_or_query, session, actividad, data: CuotaExtract, *, use_edit: bool = False,
) -> None:
    name_results = await _resolve_names(session, data.nombres, data.course)
    resolved = [r for r in name_results if r.resolved]
    not_found = [r for r in name_results if r.not_found]
    ambiguous = [r for r in name_results if r.ambiguous]

    lines = [f"💰 *Pago registrado — {actividad.nombre}*\n"]

    for r in resolved:
        _pago, participante = await register_payment(
            session,
            actividad_id=actividad.id,
            student_id=r.matched_id,
            monto=data.monto,
        )
        total = float(participante.total_pagado)
        restante = max(0.0, float(actividad.monto) - total)
        estado = "✅ Completo" if participante.is_complete else f"⚠️ Faltan ${restante:.2f}"
        lines.append(f"• {r.matched_name.title()} — ${data.monto:.2f}  {estado}")

    if not_found:
        lines.append(f"\n❌ *No encontrados:* {', '.join(r.raw_name for r in not_found)}")
    if ambiguous:
        lines.append(f"\n⚠️ *Ambiguos (no registrados):* {', '.join(r.raw_name for r in ambiguous)}")

    text = "\n".join(lines)
    if use_edit:
        await update_or_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await update_or_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def handle_pago(update, user_id: int, data: CuotaExtract) -> None:
    if not data.nombres:
        await update.message.reply_text(
            "No identifiqué a quién registrar el pago.\n_Ejemplo: García pagó $30 para el Paseo_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not data.monto:
        await update.message.reply_text(
            "No identifiqué el monto.\n_Ejemplo: García pagó $30_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    teacher_id = await _get_teacher_id(user_id)

    async with async_session() as session:
        if data.nombre:
            actividad = await get_activity_by_name(session, data.nombre)
        else:
            actividades = await get_activities(session, teacher_id=teacher_id)
            if not actividades:
                await update.message.reply_text("No hay actividades activas para registrar pagos.")
                return
            if len(actividades) == 1:
                actividad = actividades[0]
            else:
                set_pending_pago(user_id, data)
                await update.message.reply_text(
                    "¿Para qué actividad es el pago?",
                    reply_markup=_actividad_pago_keyboard(actividades),
                )
                return

        if not actividad:
            await update.message.reply_text(
                f"No encontré la actividad *{data.nombre}*.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        await _send_pago_result(update, session, actividad, data)

    logger.info(f"[cuotas] pago user={user_id} actividad={actividad.id}")


async def handle_cuota_pago_callback(update, context) -> None:
    """cuota_pago:{actividad_id} — retoma un pago pendiente con la actividad elegida."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    actividad_id = int(query.data.split(":")[1])
    await query.edit_message_reply_markup(reply_markup=None)

    data = pop_pending_pago(user_id)
    if not data:
        await query.edit_message_text("Sesión expirada. Vuelve a enviar el mensaje.")
        return

    async with async_session() as session:
        from schoolai.skills.cuotas.service import get_activity_status

        actividad, _ = await get_activity_status(session, actividad_id)
        if not actividad:
            await query.edit_message_text("Actividad no encontrada.")
            return

        await _send_pago_result(query, session, actividad, data, use_edit=True)

    logger.info(f"[cuotas] pago_callback user={user_id} actividad={actividad_id}")
