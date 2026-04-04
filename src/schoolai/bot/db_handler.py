"""DB skill handler — register people via inline keyboard flow.

Flow:
  /db  →  [rol buttons]  →  send list  →  [grade if student]
       →  [section if student]  →  preview  →  [Confirmar/Cancelar]
"""

from loguru import logger
from sqlalchemy import func, or_, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.callback_router import callback_router
from schoolai.bot.state import DbFlow, clear_db_flow, get_db_flow, set_db_flow
from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.db.models.teacher import Teacher
from schoolai.skills.db.service import link_representative, save_people, save_teacher_whatsapp, search_teachers_by_name
from schoolai.skills.db.deduplicator import build_preview_lines, deduplicate
from schoolai.skills.db.parser import parse_list
from schoolai.skills.utils.keyboards import grade_keyboard
from schoolai.skills.utils.text import normalize

# ── Roles ─────────────────────────────────────────────────────────────────────

ROLES = [
    ("Estudiante", "estudiante"),
    ("Docente", "docente"),
    ("Directivo", "directivo"),
    ("Administrativo", "administrativo"),
    ("Representante", "representante"),
]

SCHEDULE_OPTION = "horario"

SECTIONS = ["A", "B", "C", "D", "E"]


# ── Entry point: /db command ──────────────────────────────────────────────────


async def handle_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_db_flow(update.effective_user.id)
    await update.message.reply_text(
        "¿Qué deseas registrar?",
        reply_markup=_role_keyboard(),
    )


# ── Callback query dispatcher ─────────────────────────────────────────────────


@callback_router.register("db_")
async def handle_db_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    logger.info(f"[db_callback] user={user_id} data={data!r}")

    if data == "db_role:wa_docente":
        await query.edit_message_reply_markup(reply_markup=None)
        set_db_flow(user_id, DbFlow(step="wa_search_teacher", role="wa_docente"))
        await query.edit_message_text(
            "📱 *WhatsApp docente*\n\nEscribe el nombre del docente:",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "db_role:horario":
        from schoolai.bot.schedule_handler import start_schedule_flow

        await query.edit_message_reply_markup(reply_markup=None)
        await start_schedule_flow(update, context)
        return

    if data == "db_role:cargos":
        from schoolai.bot.position_handler import start_position_flow

        await query.edit_message_reply_markup(reply_markup=None)
        await start_position_flow(update, context)
        return

    if data.startswith("db_role:"):
        await _on_role(query, user_id, data.split(":", 1)[1])

    elif data.startswith("db_grade:"):
        parts = data.split(":", 2)
        await _on_grade(query, user_id, int(parts[1]), parts[2])

    elif data.startswith("db_section:"):
        await _on_section(query, user_id, data.split(":", 1)[1])

    elif data.startswith("db_link:"):
        value = data.split(":", 1)[1]
        if value == "skip":
            clear_db_flow(user_id)
            await query.edit_message_text("Vinculación omitida.")
        else:
            await _on_link_confirm(query, user_id, int(value))

    elif data.startswith("db_wa_teacher:"):
        teacher_id = int(data.split(":", 1)[1])
        await _on_wa_teacher_selected(query, user_id, teacher_id)

    elif data == "db_confirm":
        await _on_confirm(query, user_id)

    elif data == "db_cancel":
        clear_db_flow(user_id)
        await query.edit_message_text("Operación cancelada.")


# ── Step handlers ─────────────────────────────────────────────────────────────


async def _on_role(query, user_id: int, role: str) -> None:
    set_db_flow(user_id, DbFlow(step="await_list", role=role))
    await query.edit_message_text(
        f"Rol: *{role}*\n\nEnvía la lista de nombres, uno por línea.\n"
        "Puedes incluir la cédula en la misma línea:\n"
        "```\nJuan Pérez\nMaría López 0912345678\n1234567890 Carlos Torres\n```",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _on_grade(query, user_id: int, grade_id: int, grade_name: str) -> None:
    flow = get_db_flow(user_id)
    if not flow:
        await query.edit_message_text("Sesión expirada. Usa /db para empezar.")
        return
    flow.grade_id = grade_id
    flow.grade_name = grade_name
    flow.step = "await_section"
    set_db_flow(user_id, flow)
    await query.edit_message_text(
        f"Curso: *{grade_name}*\n\n¿Cuál es la sección?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_section_keyboard(),
    )


async def _on_section(query, user_id: int, section: str) -> None:
    flow = get_db_flow(user_id)
    if not flow:
        await query.edit_message_text("Sesión expirada. Usa /db para empezar.")
        return
    flow.section = section
    flow.step = "await_confirm"
    set_db_flow(user_id, flow)
    await query.edit_message_text("Verificando duplicados...")
    await _dedup_and_preview(query.edit_message_text, user_id, flow)


async def _on_confirm(query, user_id: int) -> None:
    flow = get_db_flow(user_id)
    if not flow or not flow.dedup_results:
        await query.edit_message_text("Sesión expirada. Usa /db para empezar.")
        return

    async with async_session() as session:
        result = await save_people(
            results=flow.dedup_results,
            role=flow.role,
            session=session,
            grade_id=flow.grade_id,
            section=flow.section,
        )
        # Guardar IDs creados para poder vincularlos después
        flow.saved_person_ids = [
            r.existing_id
            for r in flow.dedup_results
            if r.match_type.name == "NEW" and r.existing_id
        ]

    summary = (
        f"✅ *Guardado correctamente*\n\n"
        f"• Personas nuevas: {result.created}\n"
        f"• Omitidos (ya existen): {result.skipped}"
    )
    logger.info(f"[db] user={user_id} saved: {result}")

    # Si es representante, ofrecer vinculación a estudiante
    if flow.role == "representante" and result.created > 0:
        flow.step = "await_link_student"
        set_db_flow(user_id, flow)
        await query.edit_message_text(
            summary + "\n\n¿Deseas vincular este representante a un estudiante?\n"
            "_Envía el nombre del estudiante o escribe_ /cancelar _para saltar._",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        clear_db_flow(user_id)
        await query.edit_message_text(summary, parse_mode=ParseMode.MARKDOWN)


# ── Text message while DB flow is active ─────────────────────────────────────


async def handle_db_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    flow = get_db_flow(user_id)

    if not flow:
        return

    if flow.step == "await_link_student":
        await _on_link_student_search(update, user_id, flow)
        return

    if flow.step == "wa_search_teacher":
        await _on_wa_search_teacher(update, user_id, flow)
        return

    if flow.step == "wa_await_phone":
        await _on_wa_save_phone(update, user_id, flow)
        return

    if flow.step != "await_list":
        return

    parsed = parse_list(update.message.text)
    if not parsed:
        await update.message.reply_text(
            "No encontré ningún nombre en el mensaje. Envía un nombre por línea.",
        )
        return

    flow.parsed_names = parsed

    if flow.role == "estudiante":
        flow.step = "await_grade"
        set_db_flow(user_id, flow)
        async with async_session() as session:
            grades = (
                (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
            )
        await update.message.reply_text(
            f"Encontré *{len(parsed)} nombres*.\n\n¿A qué curso pertenecen?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "db_grade"),
        )
    else:
        # No extra data needed — go straight to preview
        flow.step = "await_confirm"
        set_db_flow(user_id, flow)
        msg = await update.message.reply_text("Verificando duplicados...")
        await _dedup_and_preview(msg.edit_text, user_id, flow)


# ── Preview ───────────────────────────────────────────────────────────────────


async def _dedup_and_preview(reply_fn, user_id: int, flow: DbFlow) -> None:
    """Run deduplication and show preview. reply_fn is an async callable (edit_text or similar)."""
    async with async_session() as session:
        results = await deduplicate(flow.parsed_names, session)

    flow.dedup_results = results
    set_db_flow(user_id, flow)

    preview_lines = build_preview_lines(results, flow.role)
    new_count = sum(1 for r in results if r.match_type.name == "NEW")
    warn_count = len(results) - new_count

    header = f"*Vista previa — {len(results)} personas*\n"
    if flow.grade_name and flow.section:
        header += f"Curso: *{flow.grade_name}* | Sección: *{flow.section}*\n"
    header += f"✅ Nuevas: {new_count}  ⚠️ Revisar: {warn_count}\n\n"

    # Split preview into chunks of 30 to avoid Telegram message limit
    chunks = [preview_lines[i : i + 30] for i in range(0, len(preview_lines), 30)]
    body = "\n".join(chunks[0])
    if len(chunks) > 1:
        body += f"\n_... y {sum(len(c) for c in chunks[1:])} más_"

    await reply_fn(
        header + body,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_confirm_keyboard(),
    )


# ── Keyboards ─────────────────────────────────────────────────────────────────


def _role_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"db_role:{value}")] for label, value in ROLES
    ]
    buttons.append([InlineKeyboardButton("📅 Horario", callback_data="db_role:horario")])
    buttons.append([InlineKeyboardButton("📋 Cargos docente", callback_data="db_role:cargos")])
    buttons.append([InlineKeyboardButton("📱 WhatsApp docente", callback_data="db_role:wa_docente")])
    return InlineKeyboardMarkup(buttons)


def _section_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(s, callback_data=f"db_section:{s}") for s in SECTIONS]],
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data="db_confirm"),
                InlineKeyboardButton("❌ Cancelar", callback_data="db_cancel"),
            ],
        ],
    )


# ── Vinculación representante ↔ estudiante ────────────────────────────────────


async def _on_link_student_search(update: Update, user_id: int, flow: DbFlow) -> None:
    """Busca el estudiante por nombre y muestra opciones para vincular."""
    query_text = update.message.text.strip()
    norm = normalize(query_text)

    async with async_session() as session:
        full_name = func.lower(Person.first_name + " " + Person.last_name)
        students = (
            (
                await session.execute(
                    select(Student)
                    .join(Student.person)
                    .where(
                        Student.status == "active",
                        or_(
                            full_name.contains(norm),
                            func.lower(Person.last_name + " " + Person.first_name).contains(norm),
                        ),
                    ),
                )
            )
            .unique()
            .scalars()
            .all()
        )

    # Final Python-side filter for normalized accents / special chars
    matches = [
        s
        for s in students
        if s.person
        and (
            norm in normalize(f"{s.person.first_name} {s.person.last_name}")
            or normalize(f"{s.person.first_name} {s.person.last_name}") in norm
        )
    ]

    if not matches:
        await update.message.reply_text(
            f"No encontré estudiantes con el nombre *{query_text}*.\n"
            "Intenta de nuevo o usa /cancelar para saltar.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if len(matches) > 8:
        await update.message.reply_text(
            f"Encontré {len(matches)} coincidencias, sé más específico.",
        )
        return

    buttons = [
        [
            InlineKeyboardButton(
                f"{s.person.first_name} {s.person.last_name} — {s.grade.name}",
                callback_data=f"db_link:{s.id}",
            ),
        ]
        for s in matches
    ]
    buttons.append([InlineKeyboardButton("❌ Saltar", callback_data="db_link:skip")])
    await update.message.reply_text(
        "¿A cuál estudiante vincular?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _on_link_confirm(query, user_id: int, student_id: int) -> None:
    """Guarda el vínculo representante ↔ estudiante."""
    flow = get_db_flow(user_id)
    if not flow or not flow.saved_person_ids:
        await query.edit_message_reply_markup(reply_markup=None)
        clear_db_flow(user_id)
        return

    person_id = flow.saved_person_ids[0]

    async with async_session() as session:
        await link_representative(
            session=session,
            student_id=student_id,
            person_id=person_id,
            make_primary=True,
        )
        student = await session.get(Student, student_id)
        name = (
            f"{student.person.first_name} {student.person.last_name}"
            if student and student.person
            else str(student_id)
        )

    clear_db_flow(user_id)
    await query.edit_message_text(
        f"✅ Representante vinculado a *{name}* como contacto primario.",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f"[db] link rep person={person_id} → student={student_id}")


# ── WhatsApp docente ───────────────────────────────────────────────────────────


async def _on_wa_search_teacher(update: Update, user_id: int, flow: DbFlow) -> None:
    """Busca docente por nombre para asignarle WhatsApp."""
    query_text = update.message.text.strip()

    async with async_session() as session:
        matches = await search_teachers_by_name(query_text, session)

    if not matches:
        await update.message.reply_text(
            f"No encontré docentes con el nombre *{query_text}*. Intenta de nuevo.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if len(matches) > 8:
        await update.message.reply_text("Demasiados resultados, sé más específico.")
        return

    buttons = [
        [InlineKeyboardButton(
            f"{t.person.first_name} {t.person.last_name}"
            + (" ✅" if t.whatsapp_phone else ""),
            callback_data=f"db_wa_teacher:{t.id}",
        )]
        for t in matches
    ]
    buttons.append([InlineKeyboardButton("❌ Cancelar", callback_data="db_cancel")])
    await update.message.reply_text(
        "¿A cuál docente asignar el número?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _on_wa_teacher_selected(query, user_id: int, teacher_id: int) -> None:
    """Muestra número actual si existe y pide el nuevo."""
    async with async_session() as session:
        teacher = await session.get(Teacher, teacher_id)
        if not teacher:
            await query.edit_message_text("Docente no encontrado.")
            clear_db_flow(user_id)
            return
        name = f"{teacher.person.first_name} {teacher.person.last_name}"
        current = teacher.whatsapp_phone

    flow = get_db_flow(user_id)
    if not flow:
        return
    flow.step = "wa_await_phone"
    flow.target_teacher_id = teacher_id
    flow.target_teacher_name = name
    set_db_flow(user_id, flow)

    current_txt = f"\nNúmero actual: `{current}`" if current else ""
    await query.edit_message_text(
        f"📱 *{name}*{current_txt}\n\n¿Cuál es su número de WhatsApp?\n_(ej: +593XXXXXXXXX)_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _on_wa_save_phone(update: Update, user_id: int, flow: DbFlow) -> None:
    """Guarda el número de WhatsApp del docente."""
    phone = update.message.text.strip().replace(" ", "")
    if not phone.startswith("+") or len(phone) < 8:
        await update.message.reply_text(
            "Formato inválido. Usa código de país, ej: +593XXXXXXXXX",
        )
        return

    async with async_session() as session:
        name = await save_teacher_whatsapp(flow.target_teacher_id, phone, session)

    if not name:
        await update.message.reply_text("Docente no encontrado.")
        clear_db_flow(user_id)
        return

    clear_db_flow(user_id)
    await update.message.reply_text(
        f"✅ WhatsApp de *{name}* guardado: `{phone}`",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f"[db] whatsapp teacher={flow.target_teacher_id} phone={phone}")
