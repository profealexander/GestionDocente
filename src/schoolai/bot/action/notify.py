"""Prompts de notificación post-tarea (WhatsApp y documentos)."""

from __future__ import annotations

from telegram.constants import ParseMode

from schoolai.bot.action._widgets import _HW_STATUS_LABELS
from schoolai.bot.notif_handler import doc_notify_keyboard
from schoolai.bot.state import PendingWhatsAppNotification, set_wa_notification
from schoolai.bot.whatsapp_handler import notify_keyboard


async def _send_notify_prompt(
    send_fn,
    user_id: int,
    hw,
    student_ids: list,
    student_names: list,
) -> None:
    """Stores WA notification state and sends the notify button.

    send_fn must be an awaitable callable: send_fn(text, **kwargs).
    Typical usage:
      bot path  → lambda t, **kw: bot.send_message(chat_id, t, **kw)
      reply_fn  → update.message.reply_text
    """
    if not student_ids or not user_id:
        return
    delivery_str = hw.delivery_date.strftime("%d/%m/%Y") if hw.delivery_date else ""
    subj = hw.subject.name if hw.subject else "sin materia"
    set_wa_notification(
        user_id,
        PendingWhatsAppNotification(
            chat_id=0,
            hw_id=hw.id,
            hw_seq=hw.sequence_num,
            subject=subj,
            grade_name=hw.grade.name if hw.grade else "",
            delivery_date=delivery_str,
            student_ids=list(student_ids),
            student_names=list(student_names),
        ),
    )
    await send_fn(
        "¿Deseas notificar a los representantes por WhatsApp?",
        reply_markup=notify_keyboard(student_ids),
    )
    await send_fn(
        "📄 Generar notificación formal:",
        reply_markup=doc_notify_keyboard(hw.id, student_ids, student_names),
    )


async def _reply_hw_report(
    bot,
    chat_id,
    hw,
    student_ids,
    student_names,
    not_found,
    status,
    total,
    user_id: int = 0,
):
    """Sends the homework report summary message and notify button."""
    subj = hw.subject.name if hw.subject else "sin materia"
    status_label = _HW_STATUS_LABELS.get(status, "No entregaron")
    missing = len(student_ids)
    lines = [f"📊 *CUMPLIMIENTO — Tarea #{hw.sequence_num}*", f"_{subj}_\n"]
    lines.append(f"✗ *{status_label} ({missing}):*")
    lines.extend(f"  • {name}" for name in student_names)
    lines.append(f"\n✓ Cumplieron: *{max(0, total - missing)} de {total}*")
    if not_found:
        lines.append(f"\n⚠️ No encontrados: {', '.join(not_found)}")
    await bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    await _send_notify_prompt(
        lambda t, **kw: bot.send_message(chat_id, t, **kw),
        user_id,
        hw,
        student_ids,
        student_names,
    )
