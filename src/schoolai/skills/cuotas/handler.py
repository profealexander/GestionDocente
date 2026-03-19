"""Lógica de interacción Telegram para cuotas — conversación, teclados, respuestas."""

from __future__ import annotations

import io

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.cuotas.extractor import CuotaExtract

# Cache de pagos pendientes esperando que el usuario elija actividad
_pending_pago: dict[int, CuotaExtract] = {}
from schoolai.skills.cuotas.service import (
    add_participantes,
    create_actividad,
    get_actividad_by_nombre,
    get_actividades,
    get_estado_actividad,
    get_students_in_grade,
    register_pago,
)
from schoolai.skills.utils.keyboards import grade_keyboard


# ── Helpers de teclado ────────────────────────────────────────────────────────

def _actividad_keyboard(actividades) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"📋 {a.nombre} (${a.monto:.0f})", callback_data=f"cuota_sel:{a.id}")]
        for a in actividades
    ]
    return InlineKeyboardMarkup(buttons)


def _actividad_pago_keyboard(actividades) -> InlineKeyboardMarkup:
    """Teclado para seleccionar actividad en contexto de registro de pago."""
    buttons = [
        [InlineKeyboardButton(f"💰 {a.nombre} (${a.monto:.0f})", callback_data=f"cuota_pago:{a.id}")]
        for a in actividades
    ]
    return InlineKeyboardMarkup(buttons)


def _cuota_grade_keyboard(actividad_id: int, grades) -> InlineKeyboardMarkup:
    """Teclado de cursos con actividad_id embebido.
    callback_data: cuota_grade:{actividad_id}:{grade_id}:{grade_name}
    """
    buttons = []
    row = []
    for g in grades:
        cb = f"cuota_grade:{actividad_id}:{g.id}:{g.name}"
        row.append(InlineKeyboardButton(g.name, callback_data=cb))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ── Handlers principales ──────────────────────────────────────────────────────

async def handle_create(update, user_id: int, data: CuotaExtract) -> None:
    if not data.nombre:
        await update.message.reply_text(
            "¿Cómo se llama la actividad? Ejemplo:\n"
            "_nueva actividad \"Paseo de Grado\" $50_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not data.monto:
        await update.message.reply_text(
            f"¿Cuánto cuesta _{data.nombre}_? Indica el monto, ej: *$50*",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Obtener teacher_id
    teacher_id = await _get_teacher_id(user_id)

    async with async_session() as session:
        actividad = await create_actividad(
            session,
            nombre=data.nombre,
            monto=data.monto,
            teacher_id=teacher_id,
        )

    logger.info(f"[cuotas] actividad creada id={actividad.id} nombre={actividad.nombre!r} user={user_id}")

    # Si indicó curso, agregar participantes automáticamente
    if data.course:
        await _add_students_from_course(update, user_id, actividad.id, data.course)
    else:
        async with async_session() as session:
            from sqlalchemy import select
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()

        await update.message.reply_text(
            f"✅ *Actividad creada:* {actividad.nombre}\n"
            f"Monto: *${actividad.monto:.2f}*\n\n"
            "¿Para qué curso agregas participantes? (o /cancelar para hacerlo después)",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_cuota_grade_keyboard(actividad.id, grades),
        )


async def handle_list(update, user_id: int) -> None:
    teacher_id = await _get_teacher_id(user_id)
    async with async_session() as session:
        actividades = await get_actividades(session, teacher_id=teacher_id)

    if not actividades:
        await update.message.reply_text("No hay actividades activas registradas.")
        return

    lines = ["📋 *Actividades activas:*\n"]
    for a in actividades:
        lines.append(f"• *{a.nombre}* — ${a.monto:.2f}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def handle_query(update, user_id: int, data: CuotaExtract) -> None:
    teacher_id = await _get_teacher_id(user_id)

    async with async_session() as session:
        # Buscar por nombre si se indicó
        if data.nombre:
            actividad = await get_actividad_by_nombre(session, data.nombre)
            if not actividad:
                await update.message.reply_text(
                    f"No encontré ninguna actividad con nombre *{data.nombre}*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return
            await _send_estado(update, actividad.id, session)
            return

        # Sin nombre → mostrar lista para elegir
        actividades = await get_actividades(session, teacher_id=teacher_id)

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


async def handle_pago(update, user_id: int, data: CuotaExtract) -> None:
    if not data.nombres:
        await update.message.reply_text(
            "No identifiqué a quién registrar el pago.\n"
            "_Ejemplo: García pagó $30 para el Paseo_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not data.monto:
        await update.message.reply_text(
            "No identifiqué el monto.\n"
            "_Ejemplo: García pagó $30_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    teacher_id = await _get_teacher_id(user_id)

    async with async_session() as session:
        # Encontrar actividad
        if data.nombre:
            actividad = await get_actividad_by_nombre(session, data.nombre)
        else:
            actividades = await get_actividades(session, teacher_id=teacher_id)
            if len(actividades) == 1:
                actividad = actividades[0]
            elif not actividades:
                await update.message.reply_text("No hay actividades activas para registrar pagos.")
                return
            else:
                _pending_pago[user_id] = data
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

        # Resolver nombres → student_ids
        extracted = [{"name": n, "status": "absent"} for n in data.nombres]

        # Buscar en curso si se indicó, sino en todos
        if data.course:
            from schoolai.skills.homework.repository import find_grade
            grade = await find_grade(session, data.course)
            grade_id = grade.id if grade else None
        else:
            # Buscar en participantes de la actividad
            grade_id = None

        if grade_id:
            name_results = await match_names(extracted, grade_id, session)
        else:
            # Sin curso: buscar en cualquier grado (primera coincidencia)
            from schoolai.db.models.grade import Grade as GradeModel
            from sqlalchemy import select
            grades = (await session.execute(select(GradeModel).where(GradeModel.is_active.is_(True)))).scalars().all()
            name_results = []
            for g in grades:
                results = await match_names(extracted, g.id, session)
                resolved = [r for r in results if r.resolved]
                if resolved:
                    name_results = results
                    break
            if not name_results:
                name_results = await match_names(extracted, grades[0].id if grades else 0, session)

        resolved   = [r for r in name_results if r.resolved]
        not_found  = [r for r in name_results if r.not_found]
        ambiguous  = [r for r in name_results if r.ambiguous]

        lines = [f"💰 *Pago registrado — {actividad.nombre}*\n"]

        for r in resolved:
            _pago, participante = await register_pago(
                session,
                actividad_id=actividad.id,
                student_id=r.matched_id,
                monto=data.monto,
            )
            total     = float(participante.total_pagado)
            restante  = max(0.0, float(actividad.monto) - total)
            estado    = "✅ Completo" if participante.is_complete else f"⚠️ Faltan ${restante:.2f}"
            lines.append(f"• {r.matched_name.title()} — ${data.monto:.2f}  {estado}")

        if not_found:
            lines.append(f"\n❌ *No encontrados:* {', '.join(r.raw_name for r in not_found)}")

        if ambiguous:
            lines.append(f"\n⚠️ *Ambiguos (no registrados):* {', '.join(r.raw_name for r in ambiguous)}")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        logger.info(f"[cuotas] pago user={user_id} actividad={actividad.id} students={len(resolved)}")


async def handle_export(update, user_id: int, data: CuotaExtract) -> None:
    from schoolai.skills.cuotas.exporter import export_actividad_excel

    teacher_id = await _get_teacher_id(user_id)

    async with async_session() as session:
        if data.nombre:
            actividad = await get_actividad_by_nombre(session, data.nombre)
            if not actividad:
                await update.message.reply_text(
                    f"No encontré la actividad *{data.nombre}*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return
        else:
            actividades = await get_actividades(session, teacher_id=teacher_id)
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
        _act, participantes = await get_estado_actividad(session, actividad_id)
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
    logger.info(f"[cuotas] export user={user_id} actividad={actividad_id} rows={len(participantes)}")


# ── Callback: elegir curso para agregar participantes ─────────────────────────

async def handle_add_grade_callback(update, context) -> None:
    """Callback cuota_grade:{actividad_id}:{grade_id}:{grade_name}."""
    query = update.callback_query
    await query.answer()

    # formato: cuota_grade:{actividad_id}:{grade_id}:{grade_name}
    parts = query.data.split(":", 3)
    if len(parts) < 4:
        await query.edit_message_text("Error en los datos del teclado.")
        return

    actividad_id = int(parts[1])
    grade_id     = int(parts[2])
    grade_name   = parts[3]

    await query.edit_message_reply_markup(reply_markup=None)
    await _add_students_from_grade_id(
        query.edit_message_text,
        update.effective_user.id,
        actividad_id, grade_id, grade_name,
    )


async def handle_cuota_sel_callback(update, context) -> None:
    """Callback cuota_sel:{actividad_id} — elegir actividad para ver estado."""
    query = update.callback_query
    await query.answer()
    actividad_id = int(query.data.split(":")[1])
    await query.edit_message_reply_markup(reply_markup=None)
    async with async_session() as session:
        await _send_estado(query, actividad_id, session, use_edit=True)


async def handle_cuota_pago_callback(update, context) -> None:
    """Callback cuota_pago:{actividad_id} — retoma un pago pendiente con la actividad elegida."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    actividad_id = int(query.data.split(":")[1])
    await query.edit_message_reply_markup(reply_markup=None)

    data = _pending_pago.pop(user_id, None)
    if not data:
        await query.edit_message_text("Sesión expirada. Vuelve a enviar el mensaje.")
        return

    # Inyectar actividad_id directamente en el flujo de pago
    async with async_session() as session:
        from schoolai.skills.cuotas.service import get_estado_actividad as _get_est
        actividad, _ = await _get_est(session, actividad_id)
        if not actividad:
            await query.edit_message_text("Actividad no encontrada.")
            return

        extracted = [{"name": n, "status": "absent"} for n in data.nombres]
        if data.course:
            from schoolai.skills.homework.repository import find_grade
            grade = await find_grade(session, data.course)
            grade_id = grade.id if grade else None
        else:
            grade_id = None

        if grade_id:
            name_results = await match_names(extracted, grade_id, session)
        else:
            from schoolai.db.models.grade import Grade as GradeModel
            from sqlalchemy import select
            grades = (await session.execute(select(GradeModel).where(GradeModel.is_active.is_(True)))).scalars().all()
            name_results = []
            for g in grades:
                results = await match_names(extracted, g.id, session)
                if any(r.resolved for r in results):
                    name_results = results
                    break
            if not name_results and grades:
                name_results = await match_names(extracted, grades[0].id, session)

        resolved  = [r for r in name_results if r.resolved]
        not_found = [r for r in name_results if r.not_found]
        ambiguous = [r for r in name_results if r.ambiguous]

        lines = [f"💰 *Pago registrado — {actividad.nombre}*\n"]
        for r in resolved:
            _pago, participante = await register_pago(
                session, actividad_id=actividad.id,
                student_id=r.matched_id, monto=data.monto,
            )
            total    = float(participante.total_pagado)
            restante = max(0.0, float(actividad.monto) - total)
            estado   = "✅ Completo" if participante.is_complete else f"⚠️ Faltan ${restante:.2f}"
            lines.append(f"• {r.matched_name.title()} — ${data.monto:.2f}  {estado}")

        if not_found:
            lines.append(f"\n❌ *No encontrados:* {', '.join(r.raw_name for r in not_found)}")
        if ambiguous:
            lines.append(f"\n⚠️ *Ambiguos:* {', '.join(r.raw_name for r in ambiguous)}")

    await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    logger.info(f"[cuotas] pago_callback user={user_id} actividad={actividad_id} students={len(resolved)}")


# ── Helpers internos ──────────────────────────────────────────────────────────

async def _get_teacher_id(user_id: int) -> int | None:
    from sqlalchemy import select
    from schoolai.db.connection import async_session as _session
    from schoolai.db.models.teacher import Teacher

    async with _session() as session:
        return (await session.execute(
            select(Teacher.id).where(
                Teacher.telegram_id == user_id,
                Teacher.is_active.is_(True),
            )
        )).scalar_one_or_none()


async def _add_students_from_course(update, user_id: int, actividad_id: int, course_abbrev: str) -> None:
    from schoolai.skills.homework.repository import find_grade

    async with async_session() as session:
        grade = await find_grade(session, course_abbrev)
        if not grade:
            await update.message.reply_text(f"No encontré el curso *{course_abbrev}*.", parse_mode=ParseMode.MARKDOWN)
            return
        students = await get_students_in_grade(session, grade.id)
        added = await add_participantes(session, actividad_id, [s.id for s in students])

    await update.message.reply_text(
        f"✅ Se agregaron *{added}* estudiantes de {grade.name} como participantes.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _add_students_from_grade_id(reply_fn, user_id: int, actividad_id: int, grade_id: int, grade_name: str) -> None:
    async with async_session() as session:
        students = await get_students_in_grade(session, grade_id)
        added = await add_participantes(session, actividad_id, [s.id for s in students])

    await reply_fn(
        f"✅ Se agregaron *{added}* estudiantes de {grade_name} como participantes.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _send_estado(target, actividad_id: int, session, use_edit: bool = False) -> None:
    actividad, participantes = await get_estado_actividad(session, actividad_id)
    if not actividad:
        msg = "Actividad no encontrada."
        if use_edit:
            await target.edit_message_text(msg)
        else:
            await target.message.reply_text(msg)
        return

    total_part  = len(participantes)
    completos   = sum(1 for p in participantes if p.is_complete)
    parciales   = sum(1 for p in participantes if not p.is_complete and float(p.total_pagado or 0) > 0)
    pendientes  = total_part - completos - parciales
    recaudado   = sum(float(p.total_pagado or 0) for p in participantes)

    lines = [
        f"📊 *CUOTAS — {actividad.nombre}*",
        f"Monto: *${actividad.monto:.2f}*  |  Participantes: {total_part}\n",
        f"✅ Completos: *{completos}*",
        f"⚠️ Parciales: *{parciales}*",
        f"❌ Pendientes: *{pendientes}*",
        f"\n💵 Recaudado: *${recaudado:.2f}* / ${float(actividad.monto) * total_part:.2f}",
    ]

    # Detalle de pendientes (máx 10 para no saturar)
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
