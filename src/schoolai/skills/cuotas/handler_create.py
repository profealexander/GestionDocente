"""Handlers de creación de actividades y callbacks post-creación."""

from __future__ import annotations

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.db.connection import async_session
from schoolai.db.models.cuota import Actividad
from schoolai.db.models.grade import Grade
from schoolai.skills.cuotas._helpers import _get_teacher_id
from schoolai.skills.cuotas.extractor import CuotaExtract
from schoolai.skills.cuotas.service import (
    add_participantes,
    create_actividad,
    get_participantes,
    get_students_in_grade,
)


# ── Teclados ──────────────────────────────────────────────────────────────────

def _action_keyboard(actividad_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Agregar curso", callback_data=f"cuota_add:{actividad_id}")],
        [InlineKeyboardButton("✅ Listo",          callback_data=f"cuota_done:{actividad_id}")],
    ])


def _pick_grade_keyboard(actividad_id: int, grades) -> InlineKeyboardMarkup:
    buttons, row = [], []
    for g in grades:
        row.append(InlineKeyboardButton(g.name, callback_data=f"cuota_pick:{actividad_id}:{g.id}:{g.name}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def _cuota_grade_keyboard(actividad_id: int, grades) -> InlineKeyboardMarkup:
    """Teclado legacy cuota_grade: (backward compat)."""
    buttons, row = [], []
    for g in grades:
        row.append(InlineKeyboardButton(g.name, callback_data=f"cuota_grade:{actividad_id}:{g.id}:{g.name}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def _pick_student_keyboard(actividad_id: int, grade_id: int, grade_name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Agregar todos", callback_data=f"cuota_addall:{actividad_id}:{grade_id}:{grade_name}")],
        [InlineKeyboardButton("📚 Otro curso",   callback_data=f"cuota_add:{actividad_id}")],
        [InlineKeyboardButton("✅ Listo",         callback_data=f"cuota_done:{actividad_id}")],
    ])


# ── Handler principal ─────────────────────────────────────────────────────────

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

    teacher_id = await _get_teacher_id(user_id)

    async with async_session() as session:
        actividad = await create_actividad(session, nombre=data.nombre, monto=data.monto, teacher_id=teacher_id)

    logger.info(f"[cuotas] actividad creada id={actividad.id} nombre={actividad.nombre!r} user={user_id}")

    added_msg = ""
    if data.course:
        async with async_session() as session:
            from schoolai.skills.homework.repository import find_grade
            grade = await find_grade(session, data.course)
            if grade:
                students = await get_students_in_grade(session, grade.id)
                added = await add_participantes(session, actividad.id, [s.id for s in students])
                added_msg = f"\n✅ {added} estudiantes de {grade.name} agregados."

    await update.message.reply_text(
        f"✅ *Actividad creada:* {actividad.nombre}\n"
        f"Monto: *${actividad.monto:.2f}*{added_msg}\n\n"
        "¿Agregar más participantes?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_action_keyboard(actividad.id),
    )


# ── Callbacks post-creación ───────────────────────────────────────────────────

async def handle_cuota_add_callback(update, context) -> None:
    """cuota_add:{actividad_id} — muestra teclado de cursos."""
    from sqlalchemy import select as _select

    query = update.callback_query
    await query.answer()
    actividad_id = int(query.data.split(":")[1])
    async with async_session() as session:
        grades = (await session.execute(_select(Grade).order_by(Grade.sort_order))).scalars().all()
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        update.effective_chat.id,
        "¿De qué curso agregas participantes?",
        reply_markup=_pick_grade_keyboard(actividad_id, grades),
    )


async def handle_cuota_pick_callback(update, context) -> None:
    """cuota_pick:{actividad_id}:{grade_id}:{grade_name} — muestra lista numerada."""
    from schoolai.bot.state import PendingCuotaCreate, set_cuota_create

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    parts = query.data.split(":", 3)
    actividad_id = int(parts[1])
    grade_id     = int(parts[2])
    grade_name   = parts[3]

    await query.edit_message_reply_markup(reply_markup=None)

    async with async_session() as session:
        students  = await get_students_in_grade(session, grade_id)
        actividad = await session.get(Actividad, actividad_id)

    if not students:
        await context.bot.send_message(
            update.effective_chat.id,
            f"No hay estudiantes activos en {grade_name}.",
            reply_markup=_action_keyboard(actividad_id),
        )
        return

    student_list = [
        {"idx": i + 1, "student_id": s.id, "name": f"{s.last_name} {s.first_name}".strip()}
        for i, s in enumerate(students)
    ]

    lines = [f"*Estudiantes de {grade_name} ({len(students)}):*\n"]
    for item in student_list:
        lines.append(f"{item['idx']}. {item['name'].title()}")
    lines.append("\n_Escribe los números separados por espacio, ej: `1 3 5`_")

    state = PendingCuotaCreate(
        actividad_id=actividad_id,
        actividad_nombre=actividad.nombre if actividad else "Actividad",
        step="await_numbers",
        grade_id=grade_id,
        grade_name=grade_name,
        student_list=student_list,
    )
    set_cuota_create(user_id, state)

    await context.bot.send_message(
        update.effective_chat.id,
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=_pick_student_keyboard(actividad_id, grade_id, grade_name),
    )


async def handle_cuota_addall_callback(update, context) -> None:
    """cuota_addall:{actividad_id}:{grade_id}:{grade_name} — agrega todos del curso."""
    from schoolai.bot.state import clear_cuota_create

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    parts = query.data.split(":", 3)
    actividad_id = int(parts[1])
    grade_id     = int(parts[2])
    grade_name   = parts[3]

    clear_cuota_create(user_id)
    await query.edit_message_reply_markup(reply_markup=None)

    async with async_session() as session:
        students = await get_students_in_grade(session, grade_id)
        added    = await add_participantes(session, actividad_id, [s.id for s in students])

    await context.bot.send_message(
        update.effective_chat.id,
        f"✅ *{added}* estudiantes de {grade_name} agregados.\n\n¿Agregar más?",
        parse_mode="Markdown",
        reply_markup=_action_keyboard(actividad_id),
    )


async def handle_cuota_done_callback(update, context) -> None:
    """cuota_done:{actividad_id} — finaliza la creación."""
    from schoolai.bot.state import clear_cuota_create

    query = update.callback_query
    await query.answer()
    user_id      = update.effective_user.id
    actividad_id = int(query.data.split(":")[1])

    clear_cuota_create(user_id)
    await query.edit_message_reply_markup(reply_markup=None)

    async with async_session() as session:
        actividad     = await session.get(Actividad, actividad_id)
        participantes = await get_participantes(session, actividad_id)

    nombre = actividad.nombre if actividad else "Actividad"
    total  = len(participantes)
    msg = (
        f"🎉 *{nombre}* lista con *{total}* participante(s)."
        if total else
        f"*{nombre}* guardada sin participantes aún."
    )
    await context.bot.send_message(update.effective_chat.id, msg, parse_mode="Markdown")


async def handle_cuota_names_text(update, user_id: int) -> bool:
    """Intercepta texto cuando hay un PendingCuotaCreate activo (step=await_numbers).
    Returns True si manejó el mensaje."""
    from schoolai.bot.state import get_cuota_create, clear_cuota_create

    state = get_cuota_create(user_id)
    if not state:
        return False

    text  = update.message.text.strip()
    parts = text.split()

    if not all(p.isdigit() for p in parts):
        await update.message.reply_text(
            "Escribe solo los números de los estudiantes separados por espacio. Ej: `1 3 5`",
            parse_mode="Markdown",
        )
        return True

    indices  = {int(p) for p in parts}
    selected = [item for item in state.student_list if item["idx"] in indices]
    invalid  = indices - {item["idx"] for item in state.student_list}

    clear_cuota_create(user_id)

    if not selected:
        await update.message.reply_text(
            "Ningún número válido. ¿Agregar más estudiantes?",
            reply_markup=_action_keyboard(state.actividad_id),
        )
        return True

    async with async_session() as session:
        added = await add_participantes(session, state.actividad_id, [s["student_id"] for s in selected])

    names = ", ".join(s["name"].title() for s in selected[:5])
    if len(selected) > 5:
        names += f" y {len(selected) - 5} más"

    lines = [f"✅ *{added}* participante(s) agregado(s) de {state.grade_name}:", f"_{names}_"]
    if invalid:
        lines.append(f"\n⚠️ Números no válidos ignorados: {', '.join(str(i) for i in sorted(invalid))}")
    lines.append("\n¿Agregar más estudiantes?")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=_action_keyboard(state.actividad_id),
    )
    return True


async def handle_add_grade_callback(update, context) -> None:
    """Legacy callback cuota_grade:{actividad_id}:{grade_id}:{grade_name}."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":", 3)
    if len(parts) < 4:
        await query.edit_message_text("Error en los datos del teclado.")
        return

    actividad_id = int(parts[1])
    grade_id     = int(parts[2])
    grade_name   = parts[3]

    await query.edit_message_reply_markup(reply_markup=None)

    async with async_session() as session:
        students = await get_students_in_grade(session, grade_id)
        added    = await add_participantes(session, actividad_id, [s.id for s in students])

    await query.edit_message_text(
        f"✅ Se agregaron *{added}* estudiantes de {grade_name} como participantes.",
        parse_mode=ParseMode.MARKDOWN,
    )
