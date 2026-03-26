"""Handler de edición de actividades (cuotas)."""

from __future__ import annotations

import re

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.db.connection import async_session
from schoolai.db.models.cuota import Actividad
from schoolai.skills.cuotas.extractor import CuotaExtract
from schoolai.skills.cuotas.service import (
    get_actividad_by_nombre,
    get_actividades,
    get_participantes,
    update_actividad,
)

# ── Teclados ──────────────────────────────────────────────────────────────────


def _edit_keyboard(actividad: Actividad) -> InlineKeyboardMarkup:
    toggle_label = "🟢 Activar" if not actividad.is_active else "🔴 Desactivar"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✏️ Nombre", callback_data=f"cuota_edit_field:{actividad.id}:nombre",
                ),
                InlineKeyboardButton(
                    "💰 Monto", callback_data=f"cuota_edit_field:{actividad.id}:monto",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📝 Descripción",
                    callback_data=f"cuota_edit_field:{actividad.id}:descripcion",
                ),
            ],
            [
                InlineKeyboardButton(
                    "➕ Agregar participante",
                    callback_data=f"cuota_edit_add_part:{actividad.id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "➖ Quitar participante",
                    callback_data=f"cuota_edit_rm_part:{actividad.id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    toggle_label, callback_data=f"cuota_edit_toggle:{actividad.id}",
                ),
            ],
        ],
    )


def _pick_keyboard(actividades) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"📋 {a.nombre} (${a.monto:.0f})",
                    callback_data=f"cuota_edit_pick:{a.id}",
                ),
            ]
            for a in actividades
        ],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _actividad_summary(actividad: Actividad) -> str:
    estado = "activa" if actividad.is_active else "inactiva"
    desc = f"\nDescripción: _{actividad.descripcion}_" if actividad.descripcion else ""
    return (
        f"✏️ *Editando actividad:* {actividad.nombre}\n"
        f"Monto: *${actividad.monto:.2f}* | Estado: {estado}{desc}\n\n"
        "¿Qué deseas modificar?"
    )


# ── Handler principal ─────────────────────────────────────────────────────────


async def handle_edit(update, user_id: int, data: CuotaExtract) -> None:
    """Punto de entrada cuando action == 'edit'."""
    from schoolai.skills.cuotas._helpers import _get_teacher_id

    teacher_id = await _get_teacher_id(user_id)

    async with async_session() as session:
        if data.nombre:
            actividad = await get_actividad_by_nombre(session, data.nombre)
            if not actividad:
                # Try including inactive
                from sqlalchemy import select

                stmt = (
                    select(Actividad)
                    .where(Actividad.nombre.ilike(f"%{data.nombre}%"))
                    .limit(1)
                )
                result = await session.execute(stmt)
                actividad = result.scalars().first()

            if not actividad:
                await update.message.reply_text(
                    f"No encontré actividad con el nombre *{data.nombre}*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

            await update.message.reply_text(
                _actividad_summary(actividad),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_edit_keyboard(actividad),
            )
            return

        # No nombre — listar actividades para elegir
        actividades = await get_actividades(session, teacher_id=teacher_id, only_active=False)

    if not actividades:
        await update.message.reply_text("No hay actividades registradas.")
        return

    await update.message.reply_text(
        "¿Qué actividad deseas editar?",
        reply_markup=_pick_keyboard(actividades),
    )


# ── Callbacks ─────────────────────────────────────────────────────────────────


async def handle_cuota_edit_pick_callback(update, context) -> None:
    """cuota_edit_pick:{actividad_id} — muestra teclado de edición."""
    query = update.callback_query
    await query.answer()

    actividad_id = int(query.data.split(":")[1])

    async with async_session() as session:
        actividad = await session.get(Actividad, actividad_id)

    if not actividad:
        await query.edit_message_text("Actividad no encontrada.")
        return

    await query.edit_message_text(
        _actividad_summary(actividad),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_edit_keyboard(actividad),
    )


async def handle_cuota_edit_field_callback(update, context) -> None:
    """cuota_edit_field:{actividad_id}:{field} — solicita el nuevo valor."""
    from schoolai.bot.state import PendingCuotaEditField, set_cuota_edit_field

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    parts = query.data.split(":")
    actividad_id = int(parts[1])
    field = parts[2]

    async with async_session() as session:
        actividad = await session.get(Actividad, actividad_id)

    if not actividad:
        await query.edit_message_text("Actividad no encontrada.")
        return

    set_cuota_edit_field(
        user_id,
        PendingCuotaEditField(
            actividad_id=actividad_id,
            actividad_nombre=actividad.nombre,
            field=field,
        ),
    )

    field_labels = {
        "nombre": "nuevo nombre",
        "monto": "nuevo monto (ej: *$75*)",
        "descripcion": "nueva descripción",
    }
    prompt = field_labels.get(field, field)

    await query.edit_message_text(
        f"Escribe el {prompt} para *{actividad.nombre}*:",
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_cuota_edit_toggle_callback(update, context) -> None:
    """cuota_edit_toggle:{actividad_id} — activa o desactiva la actividad."""
    query = update.callback_query
    await query.answer()

    actividad_id = int(query.data.split(":")[1])

    async with async_session() as session:
        actividad = await session.get(Actividad, actividad_id)
        if not actividad:
            await query.edit_message_text("Actividad no encontrada.")
            return

        new_state = not actividad.is_active
        actividad = await update_actividad(session, actividad_id, is_active=new_state)

    estado = "activada" if new_state else "desactivada"
    logger.info(
        f"[cuotas] toggle actividad id={actividad_id} is_active={new_state}",
    )

    await query.edit_message_text(
        f"✅ Actividad *{actividad.nombre}* {estado}.\n\n{_actividad_summary(actividad)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_edit_keyboard(actividad),
    )


async def handle_cuota_edit_add_part_callback(update, context) -> None:
    """cuota_edit_add_part:{actividad_id} — pide nombre del estudiante a agregar."""
    from schoolai.bot.state import PendingCuotaParticipante, set_cuota_participante

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    actividad_id = int(query.data.split(":")[1])

    async with async_session() as session:
        actividad = await session.get(Actividad, actividad_id)

    if not actividad:
        await query.edit_message_text("Actividad no encontrada.")
        return

    set_cuota_participante(
        user_id,
        PendingCuotaParticipante(actividad_id=actividad_id, actividad_nombre=actividad.nombre),
    )

    await query.edit_message_text(
        f"Escribe el nombre del estudiante a agregar a *{actividad.nombre}*:\n"
        "_Ej: Isabel Samaniego de 9egb_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_cuota_edit_rm_part_callback(update, context) -> None:
    """cuota_edit_rm_part:{actividad_id} — muestra lista de participantes para quitar."""
    from sqlalchemy import select as _select
    from sqlalchemy.orm import selectinload

    from schoolai.db.models.student import Student

    query = update.callback_query
    await query.answer()

    actividad_id = int(query.data.split(":")[1])

    async with async_session() as session:
        actividad = await session.get(Actividad, actividad_id)
        participantes = await get_participantes(session, actividad_id)

        if not participantes:
            await query.edit_message_text(
                f"*{actividad.nombre}* no tiene participantes.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Cargar nombres
        student_ids = [p.student_id for p in participantes]
        stmt = (
            _select(Student)
            .where(Student.id.in_(student_ids))
            .options(selectinload(Student.person))
        )
        students = {s.id: s for s in (await session.execute(stmt)).scalars().all()}

    buttons = []
    for p in participantes:
        s = students.get(p.student_id)
        if not s or not s.person:
            continue
        name = s.person.full_name().title()
        buttons.append([
            InlineKeyboardButton(
                f"❌ {name}",
                callback_data=f"cuota_edit_rm_confirm:{actividad_id}:{p.student_id}",
            ),
        ])

    buttons.append([
        InlineKeyboardButton("↩️ Volver", callback_data=f"cuota_edit_pick:{actividad_id}"),
    ])

    await query.edit_message_text(
        f"¿A quién quitar de *{actividad.nombre}*?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_cuota_edit_rm_confirm_callback(update, context) -> None:
    """cuota_edit_rm_confirm:{actividad_id}:{student_id} — elimina participante."""
    from sqlalchemy import delete as _delete

    from schoolai.db.models.cuota import ActividadParticipante

    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    actividad_id = int(parts[1])
    student_id = int(parts[2])

    async with async_session() as session:
        actividad = await session.get(Actividad, actividad_id)
        stmt = _delete(ActividadParticipante).where(
            ActividadParticipante.actividad_id == actividad_id,
            ActividadParticipante.student_id == student_id,
        )
        await session.execute(stmt)
        await session.commit()

    nombre_act = actividad.nombre if actividad else "Actividad"
    await query.edit_message_text(
        f"✅ Participante eliminado de *{nombre_act}*.\n\n{_actividad_summary(actividad)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_edit_keyboard(actividad),
    )


async def handle_cuota_edit_text(update, user_id: int) -> bool:
    """Intercepta texto cuando hay un PendingCuotaEditField activo.

    Returns True si manejó el mensaje.
    """
    from schoolai.bot.state import clear_cuota_edit_field, get_cuota_edit_field

    state = get_cuota_edit_field(user_id)
    if not state:
        return False

    text = update.message.text.strip()

    if state.field == "monto":
        # Parse float — accept "$50", "50", "50.5", "50,5"
        m = re.search(r"\$?\s*(\d+(?:[.,]\d{1,2})?)", text)
        if not m:
            await update.message.reply_text(
                "No pude leer el monto. Escribe un número, ej: *$75* o *75*",
                parse_mode=ParseMode.MARKDOWN,
            )
            return True
        new_value: float | str = float(m.group(1).replace(",", "."))
        kwargs = {"monto": new_value}
    elif state.field == "nombre":
        new_value = text
        kwargs = {"nombre": new_value}
    else:  # descripcion
        new_value = text
        kwargs = {"descripcion": new_value}

    clear_cuota_edit_field(user_id)

    async with async_session() as session:
        actividad = await update_actividad(session, state.actividad_id, **kwargs)

    if not actividad:
        await update.message.reply_text("No se pudo actualizar la actividad.")
        return True

    logger.info(
        f"[cuotas] edit field={state.field} actividad_id={state.actividad_id} user={user_id}",
    )

    field_labels = {"nombre": "Nombre", "monto": "Monto", "descripcion": "Descripción"}
    label = field_labels.get(state.field, state.field)

    await update.message.reply_text(
        f"✅ *{label}* actualizado.\n\n{_actividad_summary(actividad)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_edit_keyboard(actividad),
    )
    return True


# ── Auto-register ──────────────────────────────────────────────────────────────

from schoolai.bot.callback_router import callback_router  # noqa: E402
from schoolai.bot.text_interceptors import text_interceptors  # noqa: E402

callback_router.register("cuota_edit_pick:")(handle_cuota_edit_pick_callback)
callback_router.register("cuota_edit_field:")(handle_cuota_edit_field_callback)
callback_router.register("cuota_edit_toggle:")(handle_cuota_edit_toggle_callback)
callback_router.register("cuota_edit_add_part:")(handle_cuota_edit_add_part_callback)
callback_router.register("cuota_edit_rm_part:")(handle_cuota_edit_rm_part_callback)
callback_router.register("cuota_edit_rm_confirm:")(handle_cuota_edit_rm_confirm_callback)
text_interceptors.register(priority=20, name="cuota_edit_text")(handle_cuota_edit_text)
