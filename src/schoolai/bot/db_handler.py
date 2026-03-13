"""DB skill handler — register people via inline keyboard flow.

Flow:
  /db  →  [rol buttons]  →  send list  →  [grade if student]
       →  [section if student]  →  preview  →  [Confirmar/Cancelar]
"""

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.state import DbFlow, clear_db_flow, get_db_flow, set_db_flow
from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.skills.db.deduplicator import build_preview_lines, deduplicate
from schoolai.skills.db.parser import parse_list
from schoolai.skills.db.service import save_people
from schoolai.skills.utils.keyboards import grade_keyboard

from sqlalchemy import select

# ── Roles ─────────────────────────────────────────────────────────────────────

ROLES = [
    ("Estudiante", "estudiante"),
    ("Docente", "docente"),
    ("Directivo", "directivo"),
    ("Administrativo", "administrativo"),
    ("Representante", "representante"),
]

SECTIONS = ["A", "B", "C", "D", "E"]


# ── Entry point: /db command ──────────────────────────────────────────────────

async def handle_db_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_db_flow(update.effective_user.id)
    await update.message.reply_text(
        "¿Qué rol asignarás a las personas de la lista?",
        reply_markup=_role_keyboard(),
    )


# ── Callback query dispatcher ─────────────────────────────────────────────────

async def handle_db_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    logger.info(f"[db_callback] user={user_id} data={data!r}")

    if data.startswith("db_role:"):
        await _on_role(query, user_id, data.split(":", 1)[1])

    elif data.startswith("db_grade:"):
        parts = data.split(":", 2)
        await _on_grade(query, user_id, int(parts[1]), parts[2])

    elif data.startswith("db_section:"):
        await _on_section(query, user_id, data.split(":", 1)[1])

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

    clear_db_flow(user_id)

    summary = (
        f"✅ *Guardado correctamente*\n\n"
        f"• Personas nuevas: {result.created}\n"
        f"• Roles agregados: {result.role_added}\n"
        f"• Omitidos (revisar): {result.skipped}"
    )
    await query.edit_message_text(summary, parse_mode=ParseMode.MARKDOWN)
    logger.info(f"[db] user={user_id} saved: {result}")


# ── Text message while DB flow is active ─────────────────────────────────────

async def handle_db_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    flow = get_db_flow(user_id)

    if not flow or flow.step != "await_list":
        return

    parsed = parse_list(update.message.text)
    if not parsed:
        await update.message.reply_text(
            "No encontré ningún nombre en el mensaje. Envía un nombre por línea."
        )
        return

    flow.parsed_names = parsed

    if flow.role == "estudiante":
        flow.step = "await_grade"
        set_db_flow(user_id, flow)
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
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
    chunks = [preview_lines[i:i+30] for i in range(0, len(preview_lines), 30)]
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
        [InlineKeyboardButton(label, callback_data=f"db_role:{value}")]
        for label, value in ROLES
    ]
    return InlineKeyboardMarkup(buttons)


def _section_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(s, callback_data=f"db_section:{s}") for s in SECTIONS]
    ])


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="db_confirm"),
            InlineKeyboardButton("❌ Cancelar", callback_data="db_cancel"),
        ]
    ])
