"""Handler para generación y envío de notificaciones formales (PDF + Word).

Callback pattern: doc_notify:{hw_id}:{student_id}

Flow:
  1. Resolve teacher from telegram_id
  2. Register notification in DB → get num_doc
  3. Build NotificacionContext from DB
  4. Generate PDF (con firma) → send via WhatsApp to representative
  5. Generate Word (sin firma) → save to data/docs/{teacher_id}/{num_doc}.docx
  6. Report result to teacher
"""

from __future__ import annotations

import io
import os

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.callback_router import callback_router
from schoolai.config import settings
from schoolai.db.connection import async_session
from schoolai.db.models.student import Student
from schoolai.db.models.teacher import Teacher
from schoolai.db.models.whatsapp_contact import WhatsAppContact
from schoolai.skills.documents.generator import generate_pdf, generate_word, get_signature_path
from schoolai.skills.documents.notif_repository import register_notification
from schoolai.skills.documents.repository import get_notificacion_context
from schoolai.skills.whatsapp.sender import send_whatsapp_pdf

_DOCS_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "docs"),
)


def doc_notify_keyboard(
    hw_id: int, student_ids: list[int], student_names: list[str],
) -> InlineKeyboardMarkup:
    """Inline keyboard with one [📄 Notificar] button per student."""
    rows = []
    for sid, sname in zip(student_ids, student_names):
        rows.append(
            [
                InlineKeyboardButton(
                    f"📄 Notificar a {sname}",
                    callback_data=f"doc_notify:{hw_id}:{sid}",
                ),
            ],
        )
    return InlineKeyboardMarkup(rows)


@callback_router.register("doc_notify:")
async def handle_doc_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")  # doc_notify:{hw_id}:{student_id}
    hw_id = int(parts[1])
    student_id = int(parts[2])

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await query.edit_message_reply_markup(reply_markup=None)

    async with async_session() as session:
        # Resolve teacher
        teacher = (
            (await session.execute(select(Teacher).where(Teacher.telegram_id == user_id)))
            .scalars()
            .first()
        )

        if not teacher:
            await context.bot.send_message(chat_id, "❌ No encontré tu registro como docente.")
            return

        teacher_id = teacher.id

        # Register notification → num_doc
        try:
            notif_record = await register_notification(
                teacher_id=teacher_id,
                student_id=student_id,
                subject_id=None,
                homework_id=hw_id,
                notif_type="tarea",
                session=session,
            )
            num_doc = notif_record.num_doc
        except Exception as exc:
            logger.error(f"[doc_notify] register_notification failed: {exc}")
            await context.bot.send_message(chat_id, f"❌ Error al registrar la notificación: {exc}")
            return

        # Build document context
        try:
            ctx = await get_notificacion_context(
                student_id=student_id,
                hw_id=hw_id,
                teacher_id=teacher_id,
                num_doc=num_doc,
                session=session,
            )
        except Exception as exc:
            logger.error(f"[doc_notify] get_notificacion_context failed: {exc}")
            await context.bot.send_message(chat_id, f"❌ Error al obtener datos: {exc}")
            return

        # Get representative's WhatsApp phone
        rep_phone: str | None = None
        student = await session.get(Student, student_id)
        if student and student.primary_representative:
            contacts = (
                (
                    await session.execute(
                        select(WhatsAppContact).where(
                            WhatsAppContact.person_id == student.primary_representative.person_id,
                            WhatsAppContact.status == "active",
                        ),
                    )
                )
                .scalars()
                .all()
            )
            if contacts:
                rep_phone = contacts[0].phone

        await session.commit()

    # Generate documents (outside session)
    try:
        ctx.firma_path = get_signature_path(teacher_id)
        word_bytes = generate_word(ctx)
        pdf_bytes = generate_pdf(ctx)
    except Exception as exc:
        logger.error(f"[doc_notify] document generation failed: {exc}")
        await context.bot.send_message(chat_id, f"❌ Error al generar documentos: {exc}")
        return

    # Save Word to teacher folder (for future frontend)
    try:
        doc_dir = os.path.join(_DOCS_ROOT, str(teacher_id))
        os.makedirs(doc_dir, exist_ok=True)
        with open(os.path.join(doc_dir, f"{num_doc}.docx"), "wb") as f:  # noqa: ASYNC230
            f.write(word_bytes)
        logger.info(f"[doc_notify] Word saved: {doc_dir}/{num_doc}.docx")
    except Exception as exc:
        logger.warning(f"[doc_notify] no se pudo guardar Word en disco: {exc}")

    # Send PDF via WhatsApp
    wa_sent = False
    if rep_phone and settings.green_api_instance and settings.green_api_token:
        caption = f"Notificación {num_doc} — {ctx.asignatura}"
        wa_sent = await send_whatsapp_pdf(
            instance_id=settings.green_api_instance,
            token=settings.green_api_token,
            phone=rep_phone,
            pdf_bytes=pdf_bytes,
            file_name=f"{num_doc}.pdf",
            caption=caption,
        )

    # Send Word to teacher via Telegram
    await context.bot.send_document(
        chat_id,
        document=io.BytesIO(word_bytes),
        filename=f"{num_doc}.docx",
        caption=f"📄 {num_doc} — para imprimir y firmar",
    )

    # Report to teacher
    lines = [f"✅ <b>{num_doc}</b>"]
    lines.append(f"  Estudiante: {ctx.estudiante}")
    lines.append(f"  Materia: {ctx.asignatura}")
    if wa_sent:
        lines.append("📱 PDF enviado al representante por WhatsApp.")
    elif rep_phone:
        lines.append("⚠️ No se pudo enviar por WhatsApp.")
    else:
        lines.append("⚠️ El representante no tiene número de WhatsApp registrado.")

    await context.bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.HTML)
