"""Position handler — manage teacher institutional positions via /db → 📋 Cargos.

Flow:
  /db → [📋 Cargos]
      → lista de docentes → seleccionar
      → ver cargos actuales + [➕ Agregar] [🗑️ Eliminar X]
      → Agregar:
          tipo → tutor (grado) | jefe_area (área) | jefe_subnivel (subnivel)
                  | comision (texto) | cargo (valor)
          → confirmar → guardar
      → Eliminar: confirmar → desactivar
"""

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.state import (
    PositionFlow,
    clear_position_flow,
    get_position_flow,
    set_position_flow,
)
from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.skills.db.position_service import (
    add_position,
    deactivate_position,
    get_areas,
    get_teacher_with_positions,
)
from schoolai.skills.db.schedule_service import get_docentes
from schoolai.skills.utils.keyboards import grade_keyboard

# ── Constantes ────────────────────────────────────────────────────────────────

SUBNIVELES = ["inicial", "basica", "media", "bachillerato"]
SUBNIVEL_LABELS = {
    "inicial": "Inicial",
    "basica": "Básica",
    "media": "Media",
    "bachillerato": "Bachillerato",
}
CARGO_VALUES = ["rector", "vicerrector", "coordinador", "inspector", "secretaria"]
CARGO_LABELS = {
    "rector": "Rector/a",
    "vicerrector": "Vicerrector/a",
    "coordinador": "Coordinador/a",
    "inspector": "Inspector/a",
    "secretaria": "Secretaria/o",
}
POSITION_TYPE_LABELS = {
    "tutor": "📌 Tutor de curso",
    "jefe_area": "📚 Jefe de área",
    "jefe_subnivel": "🏫 Jefe de subnivel",
    "comision": "👥 Comisión",
    "cargo": "🏛️ Cargo institucional",
}

_CONFIRM_KB = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="pos_confirm"),
            InlineKeyboardButton("↩️ Volver", callback_data="pos_back"),
        ],
    ],
)


# ── Formateo ──────────────────────────────────────────────────────────────────


def _fmt(p) -> str:
    if p.position_type == "tutor":
        grade = p.grade.name if p.grade else "?"
        return f"📌 Tutor — {grade}"
    if p.position_type == "jefe_area":
        return f"📚 Jefe de área — {p.area}"
    if p.position_type == "jefe_subnivel":
        return f"🏫 Jefe de subnivel — {SUBNIVEL_LABELS.get(p.subnivel or '', p.subnivel or '?')}"
    if p.position_type == "comision":
        return f"👥 Comisión — {p.detail}"
    if p.position_type == "cargo":
        return f"🏛️ {CARGO_LABELS.get(p.detail or '', p.detail or '?')}"
    return p.position_type


# ── Entry point ───────────────────────────────────────────────────────────────


async def start_position_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    clear_position_flow(user_id)

    async with async_session() as session:
        docentes = await get_docentes(session)

    if not docentes:
        await update.effective_message.reply_text(
            "No hay docentes registrados. Usa /db → Docente para registrarlos primero.",
        )
        return

    set_position_flow(user_id, PositionFlow(step="await_teacher"))
    buttons = [
        [
            InlineKeyboardButton(
                f"{p.last_name} {p.first_name}",
                callback_data=f"pos_teacher:{p.id}",
            ),
        ]
        for p in docentes
    ]
    await update.effective_message.reply_text(
        "📋 *Cargos docentes*\n\nSelecciona el docente:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ── Callback dispatcher ───────────────────────────────────────────────────────


async def handle_position_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data.startswith("pos_teacher:"):
        await _on_teacher(query, user_id, int(data.split(":")[1]))
    elif data == "pos_add":
        await _on_add(query, user_id)
    elif data.startswith("pos_del:"):
        await _on_del_prompt(query, user_id, int(data.split(":")[1]))
    elif data.startswith("pos_type:"):
        await _on_type(query, user_id, data.split(":")[1])
    elif data.startswith("pos_grade:"):
        parts = data.split(":", 2)
        await _on_grade(query, user_id, int(parts[1]), parts[2])
    elif data.startswith("pos_subnivel:"):
        await _on_subnivel(query, user_id, data.split(":")[1])
    elif data.startswith("pos_area:"):
        await _on_area(query, user_id, int(data.split(":")[1]))
    elif data.startswith("pos_cargo:"):
        await _on_cargo(query, user_id, data.split(":")[1])
    elif data == "pos_confirm":
        await _on_confirm(query, user_id)
    elif data.startswith("pos_confirm_del:"):
        await _on_confirm_del(query, user_id, int(data.split(":")[1]))
    elif data == "pos_back":
        await _on_back(query, user_id)
    elif data == "pos_cancel":
        clear_position_flow(user_id)
        await query.edit_message_text("Operación cancelada.")


# ── Text input (comision detail) ─────────────────────────────────────────────


async def handle_position_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handles free-text input for comision detail. Returns True if handled."""
    user_id = update.effective_user.id
    flow = get_position_flow(user_id)
    if not flow or flow.step != "await_detail":
        return False

    flow.detail = update.message.text.strip()
    flow.step = "await_confirm_add"
    set_position_flow(user_id, flow)

    await update.message.reply_text(
        f"¿Confirmar cargo?\n\n*{flow.teacher_name}*\n👥 Comisión — _{flow.detail}_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CONFIRM_KB,
    )
    return True


# ── Step handlers ─────────────────────────────────────────────────────────────


async def _on_teacher(query, user_id: int, person_id: int) -> None:
    async with async_session() as session:
        teacher, positions = await get_teacher_with_positions(session, person_id=person_id)

    if not teacher:
        await query.edit_message_text(
            "Este docente no tiene perfil vinculado al bot.\n"
            "Primero debe usar /db → 📅 Horario para vincularse.",
        )
        return

    flow = get_position_flow(user_id)
    if not flow:
        return
    flow.teacher_id = teacher.id
    flow.teacher_name = f"{teacher.person.last_name} {teacher.person.first_name}"
    flow.step = "await_action"
    set_position_flow(user_id, flow)

    await _show_positions(query.edit_message_text, flow.teacher_name, positions)


async def _on_add(query, user_id: int) -> None:
    flow = get_position_flow(user_id)
    if not flow:
        return
    flow.step = "await_type"
    set_position_flow(user_id, flow)

    buttons = [
        [InlineKeyboardButton(label, callback_data=f"pos_type:{key}")]
        for key, label in POSITION_TYPE_LABELS.items()
    ]
    buttons.append([InlineKeyboardButton("↩️ Volver", callback_data="pos_back")])
    await query.edit_message_text(
        f"*{flow.teacher_name}* — Tipo de cargo:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _on_type(query, user_id: int, position_type: str) -> None:
    flow = get_position_flow(user_id)
    if not flow:
        return
    flow.position_type = position_type

    if position_type == "tutor":
        flow.step = "await_grade"
        set_position_flow(user_id, flow)
        async with async_session() as session:
            grades = (
                (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
            )
        await query.edit_message_text(
            f"*{flow.teacher_name}* — Tutor de:\n\n¿Cuál es su curso?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "pos_grade"),
        )

    elif position_type == "jefe_subnivel":
        flow.step = "await_subnivel"
        set_position_flow(user_id, flow)
        buttons = [
            [InlineKeyboardButton(SUBNIVEL_LABELS[s], callback_data=f"pos_subnivel:{s}")]
            for s in SUBNIVELES
        ]
        buttons.append([InlineKeyboardButton("↩️ Volver", callback_data="pos_back")])
        await query.edit_message_text(
            f"*{flow.teacher_name}* — Jefe de subnivel:\n\n¿Cuál?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif position_type == "jefe_area":
        flow.step = "await_area"
        async with async_session() as session:
            areas = await get_areas(session)
        flow.areas_list = areas
        set_position_flow(user_id, flow)
        buttons = [
            [InlineKeyboardButton(a, callback_data=f"pos_area:{i}")] for i, a in enumerate(areas)
        ]
        buttons.append([InlineKeyboardButton("↩️ Volver", callback_data="pos_back")])
        await query.edit_message_text(
            f"*{flow.teacher_name}* — Jefe de área:\n\n¿Cuál área?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif position_type == "cargo":
        flow.step = "await_cargo_val"
        set_position_flow(user_id, flow)
        buttons = [
            [InlineKeyboardButton(CARGO_LABELS[c], callback_data=f"pos_cargo:{c}")]
            for c in CARGO_VALUES
        ]
        buttons.append([InlineKeyboardButton("↩️ Volver", callback_data="pos_back")])
        await query.edit_message_text(
            f"*{flow.teacher_name}* — Cargo institucional:\n\n¿Cuál?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif position_type == "comision":
        flow.step = "await_detail"
        set_position_flow(user_id, flow)
        await query.edit_message_text(
            f"*{flow.teacher_name}* — Comisión\n\nEscribe el nombre de la comisión:",
            parse_mode=ParseMode.MARKDOWN,
        )


async def _on_grade(query, user_id: int, grade_id: int, grade_name: str) -> None:
    flow = get_position_flow(user_id)
    if not flow:
        return
    flow.grade_id = grade_id
    flow.grade_name = grade_name
    flow.step = "await_confirm_add"
    set_position_flow(user_id, flow)
    await query.edit_message_text(
        f"¿Confirmar cargo?\n\n*{flow.teacher_name}*\n📌 Tutor — _{grade_name}_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CONFIRM_KB,
    )


async def _on_subnivel(query, user_id: int, subnivel: str) -> None:
    flow = get_position_flow(user_id)
    if not flow:
        return
    flow.subnivel = subnivel
    flow.step = "await_confirm_add"
    set_position_flow(user_id, flow)
    label = SUBNIVEL_LABELS.get(subnivel, subnivel)
    await query.edit_message_text(
        f"¿Confirmar cargo?\n\n*{flow.teacher_name}*\n🏫 Jefe de subnivel — _{label}_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CONFIRM_KB,
    )


async def _on_area(query, user_id: int, area_index: int) -> None:
    flow = get_position_flow(user_id)
    if not flow or area_index >= len(flow.areas_list):
        return
    flow.area = flow.areas_list[area_index]
    flow.step = "await_confirm_add"
    set_position_flow(user_id, flow)
    await query.edit_message_text(
        f"¿Confirmar cargo?\n\n*{flow.teacher_name}*\n📚 Jefe de área — _{flow.area}_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CONFIRM_KB,
    )


async def _on_cargo(query, user_id: int, cargo_val: str) -> None:
    flow = get_position_flow(user_id)
    if not flow:
        return
    flow.detail = cargo_val
    flow.step = "await_confirm_add"
    set_position_flow(user_id, flow)
    label = CARGO_LABELS.get(cargo_val, cargo_val)
    await query.edit_message_text(
        f"¿Confirmar cargo?\n\n*{flow.teacher_name}*\n🏛️ _{label}_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CONFIRM_KB,
    )


async def _on_confirm(query, user_id: int) -> None:
    flow = get_position_flow(user_id)
    if not flow or not flow.teacher_id or not flow.position_type:
        await query.edit_message_text("Sesión expirada. Usa /db para empezar.")
        return

    async with async_session() as session:
        await add_position(
            session,
            teacher_id=flow.teacher_id,
            position_type=flow.position_type,
            grade_id=flow.grade_id,
            subnivel=flow.subnivel,
            area=flow.area,
            detail=flow.detail,
        )
        _, positions = await get_teacher_with_positions(session, teacher_id=flow.teacher_id)

    logger.info(
        f"[positions] added type={flow.position_type} teacher={flow.teacher_id} user={user_id}",
    )
    teacher_name = flow.teacher_name
    clear_position_flow(user_id)

    lines = [f"✅ *Cargo guardado — {teacher_name}*\n"]
    if positions:
        lines.append("*Cargos actuales:*")
        lines.extend(f"  • {_fmt(p)}" for p in positions)

    await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def _on_del_prompt(query, user_id: int, position_id: int) -> None:
    flow = get_position_flow(user_id)
    if not flow:
        return

    async with async_session() as session:
        _, positions = await get_teacher_with_positions(session, teacher_id=flow.teacher_id)

    pos = next((p for p in positions if p.id == position_id), None)
    if not pos:
        await query.edit_message_text("Cargo no encontrado.")
        return

    label = _fmt(pos)
    await query.edit_message_text(
        f"¿Eliminar este cargo?\n\n*{flow.teacher_name}*\n{label}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🗑️ Sí, eliminar", callback_data=f"pos_confirm_del:{position_id}",
                    ),
                    InlineKeyboardButton("↩️ Cancelar", callback_data="pos_back"),
                ],
            ],
        ),
    )


async def _on_confirm_del(query, user_id: int, position_id: int) -> None:
    flow = get_position_flow(user_id)
    if not flow:
        return

    async with async_session() as session:
        await deactivate_position(session, position_id)
        _, positions = await get_teacher_with_positions(session, teacher_id=flow.teacher_id)

    logger.info(f"[positions] deactivated id={position_id} user={user_id}")
    await _show_positions(query.edit_message_text, flow.teacher_name, positions)


async def _on_back(query, user_id: int) -> None:
    flow = get_position_flow(user_id)
    if not flow or not flow.teacher_id:
        clear_position_flow(user_id)
        await query.edit_message_text("Operación cancelada.")
        return

    flow.step = "await_action"
    flow.position_type = None
    flow.grade_id = flow.grade_name = flow.subnivel = flow.area = flow.detail = None
    set_position_flow(user_id, flow)

    async with async_session() as session:
        _, positions = await get_teacher_with_positions(session, teacher_id=flow.teacher_id)

    await _show_positions(query.edit_message_text, flow.teacher_name, positions)


# ── Shared view ───────────────────────────────────────────────────────────────


async def _show_positions(reply_fn, teacher_name: str, positions: list) -> None:
    lines = [f"📋 *{teacher_name}*\n"]
    buttons = []

    if positions:
        lines.append("*Cargos actuales:*")
        for p in positions:
            label = _fmt(p)
            lines.append(f"  • {label}")
            buttons.append([InlineKeyboardButton(f"🗑️ {label}", callback_data=f"pos_del:{p.id}")])
    else:
        lines.append("_Sin cargos asignados._")

    buttons.append([InlineKeyboardButton("➕ Agregar cargo", callback_data="pos_add")])
    buttons.append([InlineKeyboardButton("❌ Cancelar", callback_data="pos_cancel")])

    await reply_fn(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
