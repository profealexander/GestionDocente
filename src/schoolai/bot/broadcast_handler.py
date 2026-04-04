"""Handler de comunicados masivos a docentes vía WhatsApp.

Trigger (texto libre):
  "comunicado para todos los docentes: ..."
  "comunicado para docentes de bachillerato: ..."
  "comunicado para docentes de básica: ..."
  "comunicado para docentes de 3ro BT: ..."
  "mensaje a todos los docentes: ..."

Flujo:
  1. Detectar intent + destinatarios + mensaje en el texto
  2. Si faltan datos, preguntar paso a paso
  3. Preguntar si adjunta archivo (imagen/documento)
  4. Enviar via Green API
"""

from __future__ import annotations

import io
import re

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.state import (
    BroadcastFlow,
    clear_broadcast_flow,
    get_broadcast_flow,
    set_broadcast_flow,
)
from schoolai.config import settings
from schoolai.db.connection import async_session
from schoolai.skills.whatsapp.broadcast import (
    get_broadcast_teachers,
    send_file_broadcast,
    send_text_broadcast,
)

# ── Patrones de detección ─────────────────────────────────────────────────────

_TRIGGER_RE = re.compile(
    r"comunicado|mensaje\s+(?:para\s+)?(?:los\s+)?docentes|aviso\s+(?:para\s+)?docentes",
    re.IGNORECASE,
)
_RECIPIENT_RE = re.compile(
    r"bachillerato|b\.?t\.?|básica|basica|egb|todos|todas|"
    r"(primer[oa]|segundo|tercer[oa]|cuart[oa]|quint[oa]|sext[oa]|"
    r"séptim[oa]|septim[oa]|octav[oa]|noven[oa]|décim[oa]|decim[oa])\s*bt",
    re.IGNORECASE,
)
_MESSAGE_RE = re.compile(r"[:]\s*(.+)$", re.DOTALL)

_GRADE_NAME_TO_ID = {
    "primero bt": 13, "primer bt": 13, "1ro bt": 13, "1er bt": 13,
    "segundo bt": 14, "2do bt": 14,
    "tercero bt": 15, "3ro bt": 15, "3er bt": 15,
}


def detect_broadcast(text: str) -> bool:
    """Retorna True si el mensaje parece un comunicado a docentes."""
    return bool(_TRIGGER_RE.search(text))


def _parse_filter(text: str) -> str:
    """Extrae el filtro de destinatarios del texto."""
    t = text.lower()
    for key, grade_id in _GRADE_NAME_TO_ID.items():
        if key in t:
            return f"grade:{grade_id}"
    if re.search(r"bachillerato|b\.?t\b", t):
        return "bachillerato"
    if re.search(r"básica|basica|egb", t):
        return "basica"
    return "all"


def _parse_message(text: str) -> str:
    """Extrae el mensaje después del ':' si existe."""
    m = _MESSAGE_RE.search(text)
    return m.group(1).strip() if m else ""


# ── Entry point: llamado desde text_interceptors ──────────────────────────────


async def handle_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Intercepta mensajes de comunicado. Retorna True si fue manejado."""
    user_id = update.effective_user.id
    text = update.message.text or ""

    # Flujo activo — continuar
    flow = get_broadcast_flow(user_id)
    if flow:
        return await _continue_flow(update, context, flow)

    # Nuevo trigger
    if not detect_broadcast(text):
        return False

    filter_type = _parse_filter(text)
    message = _parse_message(text)

    # Contar destinatarios
    async with async_session() as session:
        teachers = await get_broadcast_teachers(filter_type, session)

    count = len(teachers)
    if count == 0:
        await update.message.reply_text(
            "⚠️ No hay docentes con WhatsApp registrado para ese filtro.\n"
            "Usa /db → 📱 WhatsApp docente para agregar números.",
        )
        return True

    flow = BroadcastFlow(
        step="await_message" if not message else "await_attachment",
        filter_type=filter_type,
        message=message,
        teacher_count=count,
    )
    set_broadcast_flow(user_id, flow)

    label = _filter_label(filter_type)
    if not message:
        await update.message.reply_text(
            f"📢 Comunicado para <b>{label}</b> ({count} docentes con WhatsApp).\n\n"
            "¿Cuál es el mensaje?",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"📢 Comunicado para <b>{label}</b> ({count} docentes).\n\n"
            f"Mensaje: <i>{message}</i>\n\n"
            "¿Deseas adjuntar un archivo (imagen o documento)?",
            parse_mode=ParseMode.HTML,
            reply_markup=_attachment_keyboard(),
        )
    return True


async def _continue_flow(
    update: Update, context: ContextTypes.DEFAULT_TYPE, flow: BroadcastFlow,
) -> bool:
    user_id = update.effective_user.id

    if flow.step == "await_message":
        flow.message = (update.message.text or "").strip()
        if not flow.message:
            await update.message.reply_text("El mensaje no puede estar vacío.")
            return True
        flow.step = "await_attachment"
        set_broadcast_flow(user_id, flow)
        label = _filter_label(flow.filter_type)
        await update.message.reply_text(
            f"📢 Comunicado para <b>{label}</b> ({flow.teacher_count} docentes).\n\n"
            f"Mensaje: <i>{flow.message}</i>\n\n"
            "¿Deseas adjuntar un archivo?",
            parse_mode=ParseMode.HTML,
            reply_markup=_attachment_keyboard(),
        )
        return True

    if flow.step == "await_file":
        # Recibir archivo adjunto
        doc = update.message.document or (
            update.message.photo[-1] if update.message.photo else None
        )
        if not doc:
            await update.message.reply_text("Envía un archivo (imagen o documento).")
            return True
        await _send_with_file(update, context, flow, doc)
        return True

    return False


async def handle_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja botones de adjunto."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    flow = get_broadcast_flow(user_id)
    if not flow:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if query.data == "bc_no_attach":
        await query.edit_message_reply_markup(reply_markup=None)
        await _send_text_only(query.message.chat.id, context, flow)
        clear_broadcast_flow(user_id)

    elif query.data == "bc_attach":
        flow.step = "await_file"
        set_broadcast_flow(user_id, flow)
        await query.edit_message_text(
            f"{query.message.text}\n\n📎 Envía el archivo ahora (imagen, PDF o documento).",
            parse_mode=ParseMode.HTML,
        )


# ── Envío ─────────────────────────────────────────────────────────────────────


async def _send_text_only(chat_id: int, context, flow: BroadcastFlow) -> None:
    if not settings.green_api_instance or not settings.green_api_token:
        await context.bot.send_message(chat_id, "❌ Green API no configurada.")
        return

    await context.bot.send_message(chat_id, "⏳ Enviando comunicado...")
    async with async_session() as session:
        teachers = await get_broadcast_teachers(flow.filter_type, session)
    result = await send_text_broadcast(
        settings.green_api_instance, settings.green_api_token, teachers, flow.message,
    )
    await context.bot.send_message(chat_id, _result_summary(result))


async def _send_with_file(
    update: Update, context: ContextTypes.DEFAULT_TYPE, flow: BroadcastFlow, doc,
) -> None:
    user_id = update.effective_user.id

    if not settings.green_api_instance or not settings.green_api_token:
        await update.message.reply_text("❌ Green API no configurada.")
        clear_broadcast_flow(user_id)
        return

    await update.message.reply_text("⏳ Enviando comunicado con adjunto...")

    # Descargar archivo de Telegram
    file_obj = await context.bot.get_file(doc.file_id)
    file_bytes = io.BytesIO()
    await file_obj.download_to_memory(file_bytes)
    file_name = getattr(doc, "file_name", "adjunto.pdf") or "adjunto.pdf"

    async with async_session() as session:
        teachers = await get_broadcast_teachers(flow.filter_type, session)

    result = await send_file_broadcast(
        settings.green_api_instance, settings.green_api_token,
        teachers, file_bytes.getvalue(), file_name, flow.message,
    )
    clear_broadcast_flow(user_id)
    await update.message.reply_text(_result_summary(result))
    logger.info(f"[broadcast] file={file_name} sent={len(result.sent)}")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _filter_label(filter_type: str) -> str:
    labels = {
        "all": "todos los docentes",
        "bachillerato": "docentes de Bachillerato",
        "basica": "docentes de Básica",
    }
    if filter_type.startswith("grade:"):
        return f"docentes del curso (ID {filter_type.split(':')[1]})"
    return labels.get(filter_type, filter_type)


def _result_summary(result) -> str:
    lines = [f"✅ Enviado a {len(result.sent)} docentes"]
    if result.failed:
        lines.append(f"❌ Falló: {', '.join(result.failed)}")
    return "\n".join(lines)


def _attachment_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📎 Sí, adjuntar", callback_data="bc_attach"),
        InlineKeyboardButton("Enviar sin adjunto", callback_data="bc_no_attach"),
    ]])


