"""Handler de edición de tareas (homework)."""

from __future__ import annotations

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.db.connection import async_session
from schoolai.db.models.homework import Homework

# ── Helpers ───────────────────────────────────────────────────────────────────


def _hw_summary(hw: Homework) -> str:
    subj = hw.subject.name if hw.subject else "sin materia"
    estado = "abierta" if hw.is_open else "cerrada"
    delivery = hw.delivery_date.strftime("%d/%m/%Y") if hw.delivery_date else "sin fecha"
    desc = hw.homework[:80] + ("…" if len(hw.homework) > 80 else "")
    return (
        f"✏️ *Tarea #{hw.sequence_num}* — {hw.grade.name}\n"
        f"Materia: {subj} | Entrega: {delivery} | Estado: {estado}\n"
        f"_{desc}_\n\n"
        "¿Qué deseas modificar?"
    )


def _edit_keyboard(hw: Homework) -> InlineKeyboardMarkup:
    toggle_label = "🔓 Abrir" if not hw.is_open else "🔒 Cerrar"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📝 Descripción", callback_data=f"hw_edit_field:{hw.id}:descripcion",
            ),
            InlineKeyboardButton("📅 Fecha", callback_data=f"hw_edit_field:{hw.id}:fecha"),
        ],
        [
            InlineKeyboardButton("📚 Materia", callback_data=f"hw_edit_field:{hw.id}:materia"),
            InlineKeyboardButton(toggle_label, callback_data=f"hw_edit_toggle:{hw.id}"),
        ],
    ])


def _pick_keyboard(tasks: list[Homework]) -> InlineKeyboardMarkup:
    buttons = []
    for hw in tasks:
        subj = hw.subject.name if hw.subject else "sin materia"
        label = f"#{hw.sequence_num} — {subj} | {hw.grade.name}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"hw_edit_pick:{hw.id}")])
    return InlineKeyboardMarkup(buttons)


# ── Handler principal ─────────────────────────────────────────────────────────


async def handle_hw_edit(update, user_id: int, course: str | None, hw_ref: int | None) -> None:
    from schoolai.skills.homework.repository import find_grade, find_homework_by_ref, list_open

    async with async_session() as session:
        grade = await find_grade(session, course) if course else None
        grade_id = grade.id if grade else None

        if hw_ref is not None and grade_id:
            hw = await find_homework_by_ref(session, sequence_num=hw_ref, grade_id=grade_id)
            if hw:
                await update.message.reply_text(
                    _hw_summary(hw),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=_edit_keyboard(hw),
                )
                return

        tasks = await list_open(session, grade_id=grade_id)

    if not tasks:
        suffix = f" en {grade.name}" if grade else ""
        await update.message.reply_text(f"No hay tareas abiertas{suffix}.")
        return

    await update.message.reply_text(
        "¿Qué tarea deseas editar?",
        reply_markup=_pick_keyboard(tasks),
    )


# ── Callbacks ─────────────────────────────────────────────────────────────────


async def handle_hw_edit_pick_callback(update, context) -> None:
    """hw_edit_pick:{hw_id} — muestra teclado de edición."""
    query = update.callback_query
    await query.answer()

    hw_id = int(query.data.split(":")[1])

    async with async_session() as session:
        hw = await session.get(Homework, hw_id)

    if not hw:
        await query.edit_message_text("Tarea no encontrada.")
        return

    await query.edit_message_text(
        _hw_summary(hw),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_edit_keyboard(hw),
    )


async def handle_hw_edit_field_callback(update, context) -> None:
    """hw_edit_field:{hw_id}:{field} — solicita el nuevo valor."""
    from schoolai.bot.state import PendingHwEditField, set_hw_edit_field

    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    parts = query.data.split(":")
    hw_id = int(parts[1])
    field = parts[2]

    async with async_session() as session:
        hw = await session.get(Homework, hw_id)

    if not hw:
        await query.edit_message_text("Tarea no encontrada.")
        return

    set_hw_edit_field(
        user_id,
        PendingHwEditField(
            hw_id=hw_id, hw_seq=hw.sequence_num, grade_name=hw.grade.name, field=field,
        ),
    )

    prompts = {
        "descripcion": "nueva descripción de la tarea",
        "fecha": "nueva fecha de entrega *(ej: viernes, 28/03, mañana)*",
        "materia": "nueva materia *(ej: Matemáticas)*",
    }
    prompt = prompts.get(field, field)
    await query.edit_message_text(
        f"Escribe la {prompt} para la Tarea #{hw.sequence_num} de {hw.grade.name}:",
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_hw_edit_toggle_callback(update, context) -> None:
    """hw_edit_toggle:{hw_id} — abre o cierra la tarea."""
    from schoolai.skills.homework.repository import update_homework

    query = update.callback_query
    await query.answer()

    hw_id = int(query.data.split(":")[1])

    async with async_session() as session:
        hw = await session.get(Homework, hw_id)
        if not hw:
            await query.edit_message_text("Tarea no encontrada.")
            return
        hw = await update_homework(session, hw_id, is_open=not hw.is_open)

    estado = "abierta" if hw.is_open else "cerrada"
    logger.info(f"[homework] toggle hw_id={hw_id} is_open={hw.is_open}")

    await query.edit_message_text(
        f"✅ Tarea #{hw.sequence_num} {estado}.\n\n{_hw_summary(hw)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_edit_keyboard(hw),
    )


async def handle_hw_edit_text(update, user_id: int) -> bool:
    """Intercepta texto cuando hay un PendingHwEditField activo.

    Returns True si manejó el mensaje.
    """
    from schoolai.bot.state import clear_hw_edit_field, get_hw_edit_field
    from schoolai.skills.homework.detector import extract_date
    from schoolai.skills.homework.repository import find_subject, update_homework

    state = get_hw_edit_field(user_id)
    if not state:
        return False

    text = update.message.text.strip()
    clear_hw_edit_field(user_id)

    async with async_session() as session:
        hw = await session.get(Homework, state.hw_id)
        if not hw:
            await update.message.reply_text("Tarea no encontrada.")
            return True

        if state.field == "descripcion":
            hw = await update_homework(session, state.hw_id, homework=text)

        elif state.field == "fecha":
            d = extract_date(text)
            if d is None:
                await update.message.reply_text(
                    "No pude leer la fecha. Prueba con *viernes*, *28/03* o *mañana*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return True
            hw = await update_homework(session, state.hw_id, delivery_date=d)

        elif state.field == "materia":
            subject = await find_subject(session, text)
            hw = await update_homework(
                session, state.hw_id, subject_id=subject.id if subject else None,
            )

    field_labels = {"descripcion": "Descripción", "fecha": "Fecha de entrega", "materia": "Materia"}
    label = field_labels.get(state.field, state.field)
    logger.info(f"[homework] edit field={state.field} hw_id={state.hw_id} user={user_id}")

    await update.message.reply_text(
        f"✅ *{label}* actualizada.\n\n{_hw_summary(hw)}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_edit_keyboard(hw),
    )
    return True


# ── Auto-register ──────────────────────────────────────────────────────────────

from schoolai.bot.callback_router import callback_router  # noqa: E402
from schoolai.bot.text_interceptors import text_interceptors  # noqa: E402

callback_router.register("hw_edit_pick:")(handle_hw_edit_pick_callback)
callback_router.register("hw_edit_field:")(handle_hw_edit_field_callback)
callback_router.register("hw_edit_toggle:")(handle_hw_edit_toggle_callback)
text_interceptors.register(priority=10, name="hw_edit_text")(handle_hw_edit_text)
