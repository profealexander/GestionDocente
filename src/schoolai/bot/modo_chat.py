"""MODO CHAT IA — toggle de chat libre por usuario.

El módulo se auto-registra como text interceptor (priority=1) al importarse desde main.py.
Prioridad más alta que modo_editar (priority=2) para capturar el botón 🤖 Chat IA primero.

Mientras el modo esté activo:
- Toda entrada de texto se enruta directamente a ChatSkill (agente libre).
- El botón 🚪 Salir del Chat desactiva el modo y restaura el teclado.
"""
from __future__ import annotations

from loguru import logger
from telegram import Update

from schoolai.bot.mode import is_jornada
from schoolai.bot.state import get_user_mode, set_user_mode
from schoolai.bot.text_interceptors import text_interceptors

_BTN_CHAT = "🤖 Chat IA"
_BTN_SALIR = "🚪 Salir del Chat"


async def activar_modo_chat(update: Update, user_id: int) -> None:
    from schoolai.bot.handlers import CHAT_ACTIVE_JORNADA_KEYBOARD, CHAT_ACTIVE_KEYBOARD

    set_user_mode(user_id, "chat")
    kbd = CHAT_ACTIVE_JORNADA_KEYBOARD if is_jornada() else CHAT_ACTIVE_KEYBOARD
    await update.message.reply_text(
        "🤖 *Chat IA activo*\n_Hazme cualquier pregunta. Toca 🚪 Salir del Chat para volver._",
        parse_mode="Markdown",
        reply_markup=kbd,
    )
    logger.info(f"[modo_chat] user={user_id} → chat")


async def desactivar_modo_chat(update: Update, user_id: int) -> None:
    from schoolai.bot.handlers import JORNADA_AND_EDIT_KEYBOARD, LIBRE_KEYBOARD

    set_user_mode(user_id, "registrar")
    kbd = JORNADA_AND_EDIT_KEYBOARD if is_jornada() else LIBRE_KEYBOARD
    await update.message.reply_text(
        "Volviste al modo normal.",
        reply_markup=kbd,
    )
    logger.info(f"[modo_chat] user={user_id} → registrar")


@text_interceptors.register(priority=1, name="modo_chat")
async def handle_chat_mode_text(update: Update, user_id: int) -> bool:
    """Interceptor priority=1 — captura botón Chat IA y procesa mensajes en modo chat."""
    msg = update.message
    if not msg or not msg.text:
        return False

    text = msg.text.strip()

    # Activar modo chat — siempre, independiente del modo actual
    if text == _BTN_CHAT:
        await activar_modo_chat(update, user_id)
        return True

    # Desactivar modo chat
    if text == _BTN_SALIR:
        await desactivar_modo_chat(update, user_id)
        return True

    # Solo procesar mensajes normales si el modo es chat
    if get_user_mode(user_id) != "chat":
        return False

    # Primero intentar skills específicas (asistencia, tareas, cuotas…)
    # Si hay match, las ejecutamos normalmente — no hace falta salir del chat.
    from schoolai.skills.registry import registry

    skills = registry.detect_all(text)

    if len(skills) == 1:
        await skills[0].handle(update, user_id, text)
        return True

    if len(skills) > 1:
        from schoolai.skills.planner import plan
        for skill, fragment in plan(text, skills):
            await skill.handle(update, user_id, fragment)
        return True

    # Sin match específico → ChatSkill (saltamos OrchestratorSkill)
    from schoolai.skills.ia.skill import ChatSkill

    await ChatSkill().handle(update, user_id, text)
    return True
