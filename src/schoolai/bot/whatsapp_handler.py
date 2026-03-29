"""WhatsApp notification handler (Green API).

Flow after hw_report:
  [📱 Notificar a todos]  →  wa_notify:all
    ├── guardians con whatsapp_contact activo → send immediately via Green API
    └── guardians sin número                 → PendingWhatsAppSetup (one at a time)
          await_phone → save → send → next guardian

[📱 Notificar a alumno]  →  wa_notify:{student_id}  (same but single)
"""

import asyncio

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.callback_router import callback_router
from schoolai.bot.state import (
    PendingWhatsAppNotification,
    PendingWhatsAppSetup,
    clear_wa_notification,
    clear_wa_setup,
    get_wa_notification,
    get_wa_setup,
    set_wa_notification,
    set_wa_setup,
)
from schoolai.config import settings
from schoolai.db.connection import async_session
from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.db.models.whatsapp_contact import WhatsAppContact
from schoolai.skills.whatsapp.sender import format_homework_message, send_whatsapp


def _wa_send(phone: str, message: str):
    return send_whatsapp(settings.green_api_instance, settings.green_api_token, phone, message)


# ── Public: build notify buttons after hw_report ──────────────────────────────


def notify_keyboard(student_ids: list[int]) -> InlineKeyboardMarkup:
    """Returns inline keyboard with notify buttons to attach to hw_report messages."""
    rows = [[InlineKeyboardButton("📱 Notificar a todos", callback_data="wa_notify:all")]]
    if len(student_ids) <= 5:
        rows.extend(
            [[InlineKeyboardButton(f"📱 Notificar a alumno {sid}", callback_data=f"wa_notify:{sid}")]]
            for sid in student_ids
        )
    return InlineKeyboardMarkup(rows)


# ── Callback: wa_notify:all  or  wa_notify:{student_id} ──────────────────────


@callback_router.register("wa_notify:")
async def handle_wa_notify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    scope = query.data.split(":", 1)[1]  # "all" or str(student_id)
    notif = get_wa_notification(user_id)
    if not notif:
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(
            chat_id, "La sesión de notificación expiró. Registra el cumplimiento de nuevo.",
        )
        return

    await query.edit_message_reply_markup(reply_markup=None)

    if scope == "all":
        target_ids = notif.student_ids
        target_names = notif.student_names
    else:
        sid = int(scope)
        if sid not in notif.student_ids:
            await context.bot.send_message(chat_id, "Alumno no encontrado en el reporte.")
            return
        idx = notif.student_ids.index(sid)
        target_ids = [sid]
        target_names = [notif.student_names[idx]]

    await _process_notifications(user_id, chat_id, context.bot, notif, target_ids, target_names)


async def _process_notifications(
    user_id: int,
    chat_id: int,
    bot,
    notif: PendingWhatsAppNotification,
    student_ids: list[int],
    student_names: list[str],
) -> None:
    """Load guardians, send to those with data, queue setup for those without."""
    sent_ok: list[str] = []
    sent_fail: list[str] = []
    missing_setup: list[tuple[int, str, str]] = []  # (guardian_id, guardian_name, student_name)
    no_rep: list[tuple[int, str]] = []  # (student_id, student_name) sin representante

    async with async_session() as session:
        for sid, sname in zip(student_ids, student_names):
            student = await session.get(Student, sid)
            if not student:
                sent_fail.append(f"{sname} (estudiante no encontrado)")
                continue

            # Buscar representante primario activo
            primary_rep = student.primary_representative
            if not primary_rep:
                no_rep.append((sid, sname))
                continue

            guardian: Person = await session.get(Person, primary_rep.person_id)
            if not guardian:
                sent_fail.append(f"{sname} (representante no encontrado)")
                continue

            gname = f"{guardian.first_name} {guardian.last_name}".strip()
            active_contacts = [c for c in guardian.whatsapp_contacts if c.status == "active"]

            if not active_contacts:
                missing_setup.append((guardian.id, gname, sname))
                continue

            msg = format_homework_message(
                guardian_name=gname,
                student_name=sname,
                grade_name=notif.grade_name,
                subject=notif.subject,
                hw_seq=notif.hw_seq,
                delivery_date=notif.delivery_date,
            )
            results = await asyncio.gather(*[_wa_send(c.phone, msg) for c in active_contacts])
            if any(results):
                sent_ok.append(sname)
            else:
                sent_fail.append(f"{sname} (error al enviar)")

    # Report results
    lines = []
    if sent_ok:
        lines.append(f"✅ Enviado a representantes de: {', '.join(sent_ok)}")
    if sent_fail:
        lines.append(f"❌ No se pudo enviar: {', '.join(sent_fail)}")
    if lines:
        await bot.send_message(chat_id, "\n".join(lines))

    # Priorizar: primero alumnos sin representante (crear uno nuevo), luego los que faltan número
    if no_rep:
        sid_nr, sname_nr = no_rep[0]
        # Cola restante: otros sin-rep + guardians sin número
        notif.student_ids = [t[0] for t in no_rep[1:]] + [s[0] for s in missing_setup]
        notif.student_names = [t[1] for t in no_rep[1:]] + [s[2] for s in missing_setup]
        set_wa_notification(user_id, notif)

        remaining_count = len(no_rep) - 1 + len(missing_setup)
        extra = f" (y {remaining_count} más después)" if remaining_count else ""
        setup = PendingWhatsAppSetup(
            step="await_rep_name",
            guardian_id=0,
            guardian_name="",
            student_name=sname_nr,
            student_id=sid_nr,
        )
        set_wa_setup(user_id, setup)
        await bot.send_message(
            chat_id,
            f"📱 <b>{sname_nr}</b> no tiene representante registrado{extra}.\n\n"
            f"¿Cuál es el <b>nombre completo</b> del representante?",
            parse_mode=ParseMode.HTML,
        )
        return

    if not missing_setup:
        clear_wa_notification(user_id)
        return

    # Guardians existentes sin número de WhatsApp
    guardian_id, guardian_name, student_name = missing_setup[0]
    setup = PendingWhatsAppSetup(
        step="await_phone",
        guardian_id=guardian_id,
        guardian_name=guardian_name,
        student_name=student_name,
    )
    set_wa_setup(user_id, setup)

    remaining = len(missing_setup) - 1
    extra = f" (y {remaining} más después)" if remaining else ""
    await bot.send_message(
        chat_id,
        f"📱 Para notificar al representante de <b>{student_name}</b> "
        f"({guardian_name}) necesito su número de WhatsApp{extra}.\n\n"
        f"¿Cuál es su número? (ej: +593XXXXXXXXX)",
        parse_mode=ParseMode.HTML,
    )

    notif.student_ids = [s[0] for s in missing_setup[1:]]
    notif.student_names = [s[2] for s in missing_setup[1:]]
    set_wa_notification(user_id, notif)


# ── Text handler: collect phone / apikey ──────────────────────────────────────


async def handle_wa_setup_text(update: Update) -> bool:
    """Intercepts text while a WhatsApp setup flow is active.
    Returns True if handled (caller should return)."""
    user_id = update.effective_user.id
    setup = get_wa_setup(user_id)
    if not setup:
        return False

    text = update.message.text.strip()

    if setup.step == "await_rep_name":
        # Crear la persona representante y vincularla al estudiante
        from schoolai.skills.db.service import link_representative

        name_parts = text.split()
        if len(name_parts) < 2:
            await update.message.reply_text(
                "Ingresa nombre y apellido completos, ej: <b>María López</b>",
                parse_mode=ParseMode.HTML,
            )
            return True

        first_name = " ".join(name_parts[:-1])
        last_name = name_parts[-1]

        async with async_session() as session:
            guardian = Person(
                first_name=first_name,
                last_name=last_name,
                role="parent",
                status="active",
            )
            session.add(guardian)
            await session.flush()
            await link_representative(
                session=session,
                student_id=setup.student_id,
                person_id=guardian.id,
                make_primary=True,
            )

        setup.guardian_id = guardian.id
        setup.guardian_name = f"{first_name} {last_name}"
        setup.step = "await_phone"
        set_wa_setup(user_id, setup)

        await update.message.reply_text(
            f"✅ Representante <b>{setup.guardian_name}</b> registrado "
            f"y vinculado a <b>{setup.student_name}</b>.\n\n"
            f"¿Cuál es su número de WhatsApp? (ej: +593XXXXXXXXX)",
            parse_mode=ParseMode.HTML,
        )
        return True

    if setup.step == "await_phone":
        phone = text.replace(" ", "")
        if not phone.startswith("+") or len(phone) < 8:
            await update.message.reply_text(
                "Formato inválido. Ingresa con código de país, ej: +593XXXXXXXXX",
            )
            return True

        # Save to whatsapp_contacts
        async with async_session() as session:
            existing = (
                await session.execute(
                    select(WhatsAppContact).where(
                        WhatsAppContact.person_id == setup.guardian_id,
                        WhatsAppContact.phone == phone,
                    ),
                )
            ).scalar_one_or_none()

            if not existing:
                has_any = (
                    await session.execute(
                        select(WhatsAppContact).where(
                            WhatsAppContact.person_id == setup.guardian_id,
                        ),
                    )
                ).first()
                session.add(
                    WhatsAppContact(
                        person_id=setup.guardian_id,
                        phone=phone,
                        is_primary=has_any is None,
                        status="active",
                    ),
                )
                await session.commit()

        setup.phone = phone
        await update.message.reply_text(
            f"✅ Número guardado para <b>{setup.guardian_name}</b>.",
            parse_mode=ParseMode.HTML,
        )
        clear_wa_setup(user_id)

        # Send the notification now
        notif = get_wa_notification(user_id)
        if notif:
            # Build single-student send for this guardian
            await _send_single(update.effective_chat.id, setup, notif)

            # Continue with remaining missing guardians if any
            if notif.student_ids:
                next_id = notif.student_ids[0]
                next_name = notif.student_names[0]
                async with async_session() as session:
                    student = await session.get(Student, next_id)
                    if student:
                        rep = student.primary_representative
                        if rep:
                            g = await session.get(Person, rep.person_id)
                            active = [
                                c
                                for c in (g.whatsapp_contacts if g else [])
                                if c.status == "active"
                            ]
                            if g and not active:
                                gname = f"{g.first_name} {g.last_name}".strip()
                                next_setup = PendingWhatsAppSetup(
                                    step="await_phone",
                                    guardian_id=g.id,
                                    guardian_name=gname,
                                    student_name=next_name,
                                )
                                set_wa_setup(user_id, next_setup)
                                notif.student_ids = notif.student_ids[1:]
                                notif.student_names = notif.student_names[1:]
                                set_wa_notification(user_id, notif)
                                await update.message.reply_text(
                                    f"Siguiente representante: <b>{gname}</b> "
                                    f"(alumno: {next_name})\n"
                                    "¿Cuál es su número de WhatsApp? (+593XXXXXXXXX)",
                                    parse_mode=ParseMode.HTML,
                                )
                                return True
            clear_wa_notification(user_id)
        return True

    return False


async def _send_single(
    chat_id: int, setup: PendingWhatsAppSetup, notif: PendingWhatsAppNotification,
) -> None:
    msg = format_homework_message(
        guardian_name=setup.guardian_name,
        student_name=setup.student_name,
        grade_name=notif.grade_name,
        subject=notif.subject,
        hw_seq=notif.hw_seq,
        delivery_date=notif.delivery_date,
    )
    async with async_session() as session:
        contacts = (
            (
                await session.execute(
                    select(WhatsAppContact).where(
                        WhatsAppContact.person_id == setup.guardian_id,
                        WhatsAppContact.status == "active",
                    ),
                )
            )
            .scalars()
            .all()
        )
        results = await asyncio.gather(*[_wa_send(c.phone, msg) for c in contacts])
        for c, ok in zip(contacts, results):
            logger.info(
                f"[whatsapp] post-setup send guardian={setup.guardian_id} phone={c.phone} ok={ok}",
            )
