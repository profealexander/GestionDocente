"""Handler de carga de documentos de contexto para el Bot Agente.

Canales de entrada:
  - Foto               → Gemini Vision extrae el texto
  - Documento          → Gemini lee el archivo (PDF, Excel, Word, CSV, …)
  - /contexto <texto>  → texto plano guardado directamente
  - /contexto <URL>    → página web descargada y extraída

El caption de fotos/documentos actúa como pista (hint) para la categorización.
"""

from __future__ import annotations

import asyncio
import re

from loguru import logger
from sqlalchemy import select
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.db.connection import async_session
from schoolai.db.models.teacher import Teacher

_URL_RE = re.compile(r"^https?://\S+", re.IGNORECASE)

# MIME types que Telegram reporta para documentos comunes
_MIME_LABELS = {
    "application/pdf": "PDF",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
    "application/vnd.ms-excel": "Excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
    "application/msword": "Word",
    "text/plain": "Texto",
    "text/csv": "CSV",
    "text/markdown": "Markdown",
}

_CATEGORY_LABELS = {
    "schedule":  "Horario",
    "calendar":  "Calendario escolar",
    "policies":  "Reglamentos / Normas",
    "contacts":  "Contactos",
    "notes":     "Apuntes",
    "other":     "General",
}


async def handle_context_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Procesa foto o documento enviado al bot agente."""
    user = update.effective_user
    message = update.message
    hint: str | None = (message.caption or "").strip() or None

    await message.reply_text("⏳ Leyendo archivo...")

    file_bytes: bytes | None = None
    source_type = "document"
    original_filename: str | None = None
    mime_type = "application/octet-stream"

    if message.photo:
        source_type = "photo"
        photo = message.photo[-1]
        tg_file = await context.bot.get_file(photo.file_id)
        file_bytes = bytes(await tg_file.download_as_bytearray())
        mime_type = "image/jpeg"
        original_filename = f"photo_{photo.file_id}.jpg"

    elif message.document:
        doc = message.document
        original_filename = doc.file_name or "documento"
        mime_type = doc.mime_type or "application/octet-stream"
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = bytes(await tg_file.download_as_bytearray())

    if not file_bytes:
        await message.reply_text("No se pudo descargar el archivo.")
        return

    from schoolai.skills.context.extractor import extract_from_file

    try:
        content = await extract_from_file(file_bytes, mime_type)
    except Exception as e:
        logger.error(f"[context] error extrayendo archivo: {e}")
        await message.reply_text(
            "No se pudo extraer el contenido. "
            "Intenta enviarlo como texto con <code>/contexto</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    if not content.strip():
        await message.reply_text("El archivo parece estar vacío o sin contenido legible.")
        return

    fmt_label = _MIME_LABELS.get(mime_type, "Archivo")
    await _save_and_confirm(update, user.id, content, hint, source_type, original_filename, fmt_label)


async def handle_context_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/contexto <texto o URL> — guarda texto o página web como documento de contexto."""
    body = " ".join(context.args or []).strip()
    if not body:
        await update.message.reply_text(
            "Uso:\n"
            "  <code>/contexto Mi horario es lunes a viernes…</code>\n"
            "  <code>/contexto https://sitio.edu.ec/calendario</code>\n\n"
            "O envía directamente una foto, PDF, Excel o Word "
            "(con descripción opcional como caption).",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text("⏳ Procesando...")

    if _URL_RE.match(body):
        from schoolai.skills.context.extractor import extract_from_url
        try:
            content = await extract_from_url(body)
        except Exception as e:
            logger.error(f"[context] error cargando URL {body!r}: {e}")
            await update.message.reply_text(
                f"No se pudo cargar la página: <code>{e}</code>",
                parse_mode=ParseMode.HTML,
            )
            return
        hint = body
        source_type = "url"
        fmt_label = "Web"
    else:
        content = body
        hint = None
        source_type = "text"
        fmt_label = "Texto"

    if not content.strip():
        await update.message.reply_text("No se encontró contenido en esa fuente.")
        return

    await _save_and_confirm(update, update.effective_user.id, content, hint, source_type, None, fmt_label)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _save_and_confirm(
    update: Update,
    telegram_id: int,
    content: str,
    hint: str | None,
    source_type: str,
    original_filename: str | None,
    fmt_label: str,
) -> None:
    """Responde inmediatamente y categoriza + guarda en background."""
    processing_msg = await update.message.reply_text("⏳ Categorizando y guardando...")
    asyncio.get_event_loop().create_task(
        _categorize_and_save(
            telegram_id, content, hint, source_type,
            original_filename, fmt_label, processing_msg,
        )
    )


async def _categorize_and_save(
    telegram_id: int,
    content: str,
    hint: str | None,
    source_type: str,
    original_filename: str | None,
    fmt_label: str,
    processing_msg,
) -> None:
    """Task en background: categoriza, guarda en BD y edita el mensaje de confirmación."""
    from schoolai.skills.context.categorizer import categorize
    from schoolai.skills.context.repository import save_document

    try:
        meta = await categorize(content, hint=hint)

        async with async_session() as session:
            teacher = (
                await session.execute(select(Teacher).where(Teacher.telegram_id == telegram_id))
            ).scalar_one_or_none()
            if not teacher:
                await processing_msg.edit_text("No tienes un perfil de docente vinculado.")
                return

            saved = await save_document(
                session,
                teacher_id=teacher.id,
                scope=meta["scope"],
                category=meta["category"],
                title=meta["title"],
                content=content,
                source_type=source_type,
                original_filename=original_filename,
                hint=hint,
            )

        scope_icon = "🏫 Institucional" if meta["scope"] == "institution" else "👤 Personal"
        cat_label = _CATEGORY_LABELS.get(meta["category"], meta["category"])

        await processing_msg.edit_text(
            f"✅ <b>Guardado</b> (#{saved.id})\n\n"
            f"<b>Título:</b> {meta['title']}\n"
            f"<b>Tipo:</b> {fmt_label} · {cat_label}\n"
            f"<b>Alcance:</b> {scope_icon}\n\n"
            f"<i>Ya puedo responder preguntas usando este contenido.</i>",
            parse_mode=ParseMode.HTML,
        )
        logger.info(
            f"[context] #{saved.id} teacher={teacher.id} "
            f"scope={meta['scope']} cat={meta['category']} src={source_type}",
        )

    except Exception as e:
        logger.error(f"[context] error en background categorize+save: {e}")
        await processing_msg.edit_text(
            "❌ Error al guardar el documento. Intenta de nuevo.",
        )
