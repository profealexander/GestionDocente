"""Handlers de consulta, estado y exportación de actividades."""

from __future__ import annotations

import io

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.db.connection import async_session
from schoolai.skills.cuotas._helpers import _get_teacher_id
from schoolai.skills.cuotas.extractor import CuotaExtract
from schoolai.skills.cuotas.service import (
    get_activities,
    get_activity_by_name,
    get_activity_status,
)


def _actividad_keyboard(actividades) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"📋 {a.nombre} (${a.monto:.0f})", callback_data=f"cuota_sel:{a.id}",
                ),
            ]
            for a in actividades
        ],
    )


async def _send_estado(target, actividad_id: int, session, *, use_edit: bool = False) -> None:
    actividad, participantes = await get_activity_status(session, actividad_id)
    if not actividad:
        msg = "Actividad no encontrada."
        if use_edit:
            await target.edit_message_text(msg)
        else:
            await target.message.reply_text(msg)
        return

    total_part = len(participantes)
    completos = sum(1 for p in participantes if p.is_complete)
    parciales = sum(
        1 for p in participantes if not p.is_complete and float(p.total_pagado or 0) > 0
    )
    pendientes = total_part - completos - parciales
    recaudado = sum(float(p.total_pagado or 0) for p in participantes)

    lines = [
        f"📊 *CUOTAS — {actividad.nombre}*",
        f"Monto: *${actividad.monto:.2f}*  |  Participantes: {total_part}\n",
        f"✅ Completos: *{completos}*",
        f"⚠️ Parciales: *{parciales}*",
        f"❌ Pendientes: *{pendientes}*",
        f"\n💵 Recaudado: *${recaudado:.2f}* / ${float(actividad.monto) * total_part:.2f}",
    ]

    pending_list = [p for p in participantes if not p.is_complete][:10]
    if pending_list:
        lines.append("\n*Pendientes:*")
        for p in pending_list:
            name = p.student.last_name.title() if p.student and p.student.last_name else "—"
            pagado = float(p.total_pagado or 0)
            lines.append(f"  • {name} (${pagado:.0f}/${actividad.monto:.0f})")
        if len([p for p in participantes if not p.is_complete]) > 10:
            lines.append("  _(y más…)_")

    text = "\n".join(lines)
    if use_edit:
        await target.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        await target.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def handle_list(update, user_id: int) -> None:
    teacher_id = await _get_teacher_id(user_id)
    async with async_session() as session:
        actividades = await get_activities(session, teacher_id=teacher_id)

    if not actividades:
        await update.message.reply_text("No hay actividades activas registradas.")
        return

    lines = ["📋 *Actividades activas:*\n"]
    lines.extend(f"• *{a.nombre}* — ${a.monto:.2f}" for a in actividades)
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def handle_query(update, user_id: int, data: CuotaExtract) -> None:
    teacher_id = await _get_teacher_id(user_id)

    async with async_session() as session:
        if data.nombre:
            actividad = await get_activity_by_name(session, data.nombre)
            if not actividad:
                await update.message.reply_text(
                    f"No encontré ninguna actividad con nombre *{data.nombre}*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return
            await _send_estado(update, actividad.id, session)
            return

        actividades = await get_activities(session, teacher_id=teacher_id)

    if not actividades:
        await update.message.reply_text("No hay actividades activas.")
        return

    if len(actividades) == 1:
        async with async_session() as session:
            await _send_estado(update, actividades[0].id, session)
        return

    await update.message.reply_text(
        "¿De qué actividad quieres ver el estado?",
        reply_markup=_actividad_keyboard(actividades),
    )


async def handle_export(update, user_id: int, data: CuotaExtract) -> None:
    from schoolai.skills.cuotas.exporter import export_actividad_excel

    teacher_id = await _get_teacher_id(user_id)

    async with async_session() as session:
        if data.nombre:
            actividad = await get_activity_by_name(session, data.nombre)
            if not actividad:
                await update.message.reply_text(
                    f"No encontré la actividad *{data.nombre}*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return
        else:
            actividades = await get_activities(session, teacher_id=teacher_id)
            if not actividades:
                await update.message.reply_text("No hay actividades activas.")
                return
            if len(actividades) == 1:
                actividad = actividades[0]
            else:
                await update.message.reply_text(
                    "¿Qué actividad exportar?",
                    reply_markup=_actividad_keyboard(actividades),
                )
                return

        actividad_id = actividad.id
        _act, participantes = await get_activity_status(session, actividad_id)
        if not participantes:
            await update.message.reply_text(
                f"La actividad *{actividad.nombre}* no tiene participantes aún.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        xlsx_bytes = export_actividad_excel(actividad, participantes)

    filename = f"cuotas_{actividad.nombre.lower().replace(' ', '_')}.xlsx"
    await update.message.reply_document(
        document=io.BytesIO(xlsx_bytes),
        filename=filename,
        caption=f"📊 Reporte: *{actividad.nombre}*",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(
        f"[cuotas] export user={user_id} actividad={actividad_id} rows={len(participantes)}",
    )


async def handle_cuota_sel_callback(update, context) -> None:
    """cuota_sel:{actividad_id} — elegir actividad para ver estado."""
    query = update.callback_query
    await query.answer()
    actividad_id = int(query.data.split(":")[1])
    await query.edit_message_reply_markup(reply_markup=None)
    async with async_session() as session:
        await _send_estado(query, actividad_id, session, use_edit=True)
