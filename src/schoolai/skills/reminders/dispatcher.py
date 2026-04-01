"""Dispatcher de recordatorios — job periódico que envía los recordatorios vencidos.

Se registra en _post_init() de ambos bots:
    app.job_queue.run_repeating(job_dispatch_reminders, interval=300, first=60)
"""

from __future__ import annotations

import asyncio

from loguru import logger
from telegram.ext import ContextTypes

from schoolai.db.connection import async_session
from schoolai.skills.reminders.repository import get_due_reminders, mark_sent


async def job_dispatch_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía todos los recordatorios pendientes cuya hora ya llegó."""
    async with async_session() as session:
        reminders = await get_due_reminders(session)

    if not reminders:
        return

    logger.info(f"[reminders] dispatcher — {len(reminders)} recordatorio(s) pendiente(s)")
    await asyncio.gather(*[_dispatch_one(r, context.bot) for r in reminders])


async def _dispatch_one(reminder, bot) -> None:
    ok_tg = True
    ok_wa = True

    if reminder.target in ("teacher", "both"):
        ok_tg = await _send_telegram(reminder, bot)

    if reminder.target in ("parents", "both"):
        ok_wa = await _send_whatsapp_to_parents(reminder)

    async with async_session() as session:
        await mark_sent(session, reminder.id, ok=ok_tg and ok_wa)


async def _send_telegram(reminder, bot) -> bool:
    teacher = reminder.teacher
    if not teacher or not teacher.telegram_id:
        logger.warning(f"[reminders] recordatorio id={reminder.id}: docente sin telegram_id")
        return False
    try:
        await bot.send_message(
            chat_id=teacher.telegram_id,
            text=f"🔔 <b>Recordatorio</b>\n\n{reminder.message}",
            parse_mode="HTML",
        )
        logger.info(
            f"[reminders] Telegram enviado → teacher={teacher.telegram_id} id={reminder.id}",
        )
        return True
    except Exception as e:
        logger.error(f"[reminders] Telegram error id={reminder.id}: {e}")
        return False


async def _send_whatsapp_to_parents(reminder) -> bool:
    if not reminder.grade_id:
        logger.warning(f"[reminders] recordatorio id={reminder.id}: sin grade_id para WhatsApp")
        return False

    from sqlalchemy import select

    from schoolai.config import settings
    from schoolai.db.connection import async_session
    from schoolai.db.models.person import Person
    from schoolai.db.models.student import Student
    from schoolai.db.models.whatsapp_contact import WhatsAppContact
    from schoolai.skills.whatsapp.sender import send_whatsapp

    if not settings.green_api_instance or not settings.green_api_token:
        logger.warning("[reminders] WhatsApp no configurado (GREEN_API_INSTANCE/TOKEN ausentes)")
        return False

    async with async_session() as session:
        students = (
            (
                await session.execute(
                    select(Student).where(
                        Student.grade_id == reminder.grade_id,
                        Student.status == "active",
                    ),
                )
            )
            .scalars()
            .all()
        )

        phones: list[str] = []
        for student in students:
            rep = student.primary_representative
            if not rep:
                continue
            guardian: Person | None = await session.get(Person, rep.person_id)
            if not guardian:
                continue
            contacts = (
                (
                    await session.execute(
                        select(WhatsAppContact).where(
                            WhatsAppContact.person_id == guardian.id,
                            WhatsAppContact.status == "active",
                        ),
                    )
                )
                .scalars()
                .all()
            )
            phones.extend(c.phone for c in contacts)

    if not phones:
        logger.warning(
            f"[reminders] id={reminder.id} grade_id={reminder.grade_id}: "
            "ningún representante con WhatsApp activo",
        )
        return True  # no es un error del sistema, es un dato faltante

    grade_name = reminder.grade.name if reminder.grade else f"grade#{reminder.grade_id}"
    text = f"📢 {grade_name}\n\n{reminder.message}\n— SchoolAI"

    results = await asyncio.gather(
        *[
            send_whatsapp(settings.green_api_instance, settings.green_api_token, phone, text)
            for phone in phones
        ],
    )
    ok_count = sum(1 for r in results if r)
    logger.info(
        f"[reminders] WhatsApp id={reminder.id} → {ok_count}/{len(phones)} enviados",
    )
    return ok_count > 0
