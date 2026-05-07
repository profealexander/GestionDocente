"""MODO REGISTRAR / MODO EDITAR — toggle de modo de trabajo por usuario.

El módulo se auto-registra como text interceptor (priority=2) y como
handler de callbacks "edit_mode:" al importarse desde main.py.
"""
from __future__ import annotations

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from schoolai.bot.mode import is_jornada
from schoolai.bot.state import get_conversation_ctx, get_user_mode, set_user_mode
from schoolai.bot.text_interceptors import text_interceptors

# Textos de los botones persistentes
_BTN_EDITAR = "✏️ Modo Editar"
_BTN_REGISTRAR = "📋 Modo Registrar"


async def activar_modo_editar(update: Update, user_id: int) -> None:
    from schoolai.bot.handlers import EDIT_ACTIVE_JORNADA_KEYBOARD, EDIT_ACTIVE_KEYBOARD

    set_user_mode(user_id, "editar")
    kbd = EDIT_ACTIVE_JORNADA_KEYBOARD if is_jornada() else EDIT_ACTIVE_KEYBOARD
    await update.message.reply_text(
        "✏️ *MODO EDITAR activo*\n_Escribe qué quieres modificar o usa los menús._",
        parse_mode="Markdown",
        reply_markup=kbd,
    )
    logger.info(f"[modo_editar] user={user_id} → editar")


async def activar_modo_registrar(update: Update, user_id: int) -> None:
    from schoolai.bot.handlers import JORNADA_AND_EDIT_KEYBOARD, LIBRE_KEYBOARD

    set_user_mode(user_id, "registrar")
    kbd = JORNADA_AND_EDIT_KEYBOARD if is_jornada() else LIBRE_KEYBOARD
    await update.message.reply_text(
        "📋 *MODO REGISTRAR activo*",
        parse_mode="Markdown",
        reply_markup=kbd,
    )
    logger.info(f"[modo_editar] user={user_id} → registrar")


async def _show_edit_menu(update: Update) -> None:
    """Muestra menú de selección cuando no hay contexto previo."""
    await update.message.reply_text(
        "✏️ *¿Qué quieres editar?*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Asistencia", callback_data="edit_mode:attendance")],
            [InlineKeyboardButton("📚 Tareas",     callback_data="edit_mode:homework")],
        ]),
    )


@text_interceptors.register(priority=2, name="modo_editar")
async def handle_edit_mode_text(update: Update, user_id: int) -> bool:
    """Interceptor priority=2 — captura botones de toggle y rutas en modo editar."""
    msg = update.message
    if not msg or not msg.text:
        return False

    text = msg.text.strip()

    # Capturar pulsaciones de botón de toggle — siempre, independiente del modo
    if text == _BTN_EDITAR:
        await activar_modo_editar(update, user_id)
        return True
    if text == _BTN_REGISTRAR:
        await activar_modo_registrar(update, user_id)
        return True

    # Solo interceptar si el modo es editar
    if get_user_mode(user_id) != "editar":
        return False

    ctx = get_conversation_ctx(user_id)

    if ctx and ctx.last_intent == "attendance":
        from schoolai.skills.homework.detector import extract_date
        from schoolai.skills.attendance.handler_edit import handle_att_edit

        att_date = extract_date(text)
        await handle_att_edit(update, user_id, ctx.grade_name, att_date)
        return True

    if ctx and ctx.last_intent == "homework":
        from schoolai.skills.homework.handler_edit import handle_hw_edit

        await handle_hw_edit(update, user_id, ctx.grade_id)
        return True

    # Sin contexto previo: mostrar menú de selección
    await _show_edit_menu(update)
    return True


# ── Callbacks edit_mode: ──────────────────────────────────────────────────────

from schoolai.bot.callback_router import callback_router  # noqa: E402


@callback_router.register("edit_mode:")
async def handle_edit_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa selección del menú de edición cuando no hay contexto previo."""
    from schoolai.bot.state import set_conversation_ctx

    q = update.callback_query
    await q.answer()
    user_id = update.effective_user.id
    action = q.data.split(":", 1)[1]  # "attendance" | "homework"

    intent_map = {
        "attendance": "attendance",
        "homework": "homework",
    }
    if action not in intent_map:
        logger.warning(f"[edit_mode_callback] unknown action={action!r}")
        return

    set_conversation_ctx(user_id, intent_map[action])

    prompts = {
        "attendance": "✏️ *Editar asistencia*\nEscribe el curso o el nombre del estudiante.",
        "homework": "✏️ *Editar tarea*\nEscribe el nombre de la tarea o el curso.",
    }
    await q.edit_message_text(prompts[action], parse_mode="Markdown")
    logger.info(f"[edit_mode_callback] user={user_id} intent={action}")
