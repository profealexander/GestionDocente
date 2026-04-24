"""Schedule handler — register teacher schedules via /db → Horario flow.

Flow:
  /db → [📅 Horario]
      → (if new teacher) show docentes list → link telegram_id
      → select day of week
      → send periods as free text: "07:00-08:30 3BT Matemáticas"
      → preview → [Confirmar / Cancelar]
"""

import asyncio

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.callback_router import callback_router
from schoolai.bot.state import (
    DAY_NAMES,
    ScheduleFlow,
    clear_schedule_flow,
    get_schedule_flow,
    set_schedule_flow,
)
from schoolai.db.connection import get_db_session
from schoolai.skills.db.schedule_parser import parse_schedule_text
from schoolai.skills.db.schedule_service import (
    get_docentes,
    get_or_create_teacher,
    get_teacher_by_telegram,
    save_schedule_periods,
)
from schoolai.skills.homework.repository import find_subject
from schoolai.skills.utils.courses import course_abbrev_map

# ── Entry point (called from db_handler) ──────────────────────────────────────


async def start_schedule_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    telegram_id = update.effective_user.id
    clear_schedule_flow(user_id)

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, telegram_id)

    if teacher:
        # Already linked — go straight to day selection
        flow = ScheduleFlow(step="await_day", teacher_id=teacher.id)
        set_schedule_flow(user_id, flow)
        await update.effective_message.reply_text(
            "¿Para qué día vas a registrar el horario?",
            reply_markup=_DAY_KEYBOARD,
        )
    else:
        # Need to link this telegram account to a person
        async with get_db_session() as session:
            docentes = await get_docentes(session)

        if not docentes:
            await update.effective_message.reply_text(
                "No hay docentes registrados. Primero regístralos con /db → Docente.",
            )
            return

        flow = ScheduleFlow(step="await_teacher")
        set_schedule_flow(user_id, flow)

        buttons = [
            [
                InlineKeyboardButton(
                    f"{p.last_name} {p.first_name}",
                    callback_data=f"sch_teacher:{p.id}",
                ),
            ]
            for p in docentes
        ]
        await update.effective_message.reply_text(
            "¿Cuál de estos docentes eres tú?\n_Se vinculará tu cuenta de Telegram._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# ── Callback dispatcher ───────────────────────────────────────────────────────


@callback_router.register("sch_")
async def handle_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if data.startswith("sch_teacher:"):
        await _on_teacher(query, user_id, int(data.split(":")[1]))
    elif data.startswith("sch_day:"):
        await _on_day(query, user_id, int(data.split(":")[1]))
    elif data == "sch_confirm":
        await _on_confirm(query, user_id)
    elif data == "sch_cancel":
        clear_schedule_flow(user_id)
        await query.edit_message_text("Operación cancelada.")


# ── Step handlers ─────────────────────────────────────────────────────────────


async def _on_teacher(query, user_id: int, person_id: int) -> None:
    telegram_id = user_id
    async with get_db_session() as session:
        teacher = await get_or_create_teacher(session, person_id, telegram_id)

    flow = ScheduleFlow(step="await_day", teacher_id=teacher.id)
    set_schedule_flow(user_id, flow)
    await query.edit_message_text(
        "✅ Cuenta vinculada.\n\n¿Para qué día vas a registrar el horario?",
        reply_markup=_DAY_KEYBOARD,
    )


async def _on_day(query, user_id: int, day: int) -> None:
    flow = get_schedule_flow(user_id)
    if not flow:
        await query.edit_message_text("Sesión expirada. Usa /db para empezar.")
        return

    flow.day_of_week = day
    flow.step = "await_periods"
    set_schedule_flow(user_id, flow)

    day_name = DAY_NAMES[day]
    await query.edit_message_text(
        f"📅 *{day_name}* — envía los períodos, uno por línea:\n\n"
        "```\n"
        "07:00-08:30 3BT Matemáticas\n"
        "08:30-10:00 2BT Física\n"
        "10:30-12:00 10EGB Lengua y Literatura\n"
        "```\n"
        "_Formato: HH:MM-HH:MM CURSO MATERIA_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_schedule_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handles free-text period input. Returns True if handled."""
    user_id = update.effective_user.id
    flow = get_schedule_flow(user_id)
    if not flow or flow.step != "await_periods":
        return False

    parse_result = parse_schedule_text(update.message.text)

    if not parse_result.periods:
        await update.message.reply_text(
            "No pude interpretar ningún período. Usa el formato:\n`07:00-08:30 3BT Matemáticas`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return True

    # Resolve course abbrevs → grade_ids and subject names → subject_ids
    resolved: list[dict] = []
    unresolved: list[str] = list(parse_result.errors)

    async with get_db_session() as session:
        # Batch: buscar todas las materias en paralelo
        subjects = await asyncio.gather(
            *[find_subject(session, p.subject_raw) for p in parse_result.periods],
        )

        for i, (p, subject) in enumerate(zip(parse_result.periods, subjects), 1):
            grade_id = course_abbrev_map.get(p.course_abbrev)
            if not grade_id:
                unresolved.append(
                    f"{p.start_time}-{p.end_time} {p.course_abbrev} (curso no encontrado)",
                )
                continue

            if not subject:
                unresolved.append(
                    f"{p.start_time}-{p.end_time} {p.course_abbrev} "
                    f"{p.subject_raw} (materia no encontrada)",
                )
                continue

            resolved.append(
                {
                    "period_num": i,
                    "start_time": p.start_time,
                    "end_time": p.end_time,
                    "grade_id": grade_id,
                    "grade_name": p.course_abbrev.upper(),
                    "subject_id": subject.id,
                    "subject_name": subject.name,
                },
            )

    if not resolved:
        await update.message.reply_text(
            "No pude resolver ningún período. Verifica los cursos y materias.",
        )
        return True

    flow.parsed_periods = resolved
    flow.errors = unresolved
    flow.step = "await_confirm"
    set_schedule_flow(user_id, flow)

    day_name = DAY_NAMES[flow.day_of_week]
    lines = [f"📅 *Vista previa — {day_name}*\n"]
    lines.extend(
        f"  {p['start_time']}–{p['end_time']}  {p['grade_name']}  {p['subject_name']}"
        for p in resolved
    )

    if unresolved:
        lines.append("\n⚠️ *No reconocidos:*")
        lines.extend(f"  • {e}" for e in unresolved)

    lines.append(f"\n_{len(resolved)} período(s) listos para guardar._")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_CONFIRM_KEYBOARD,
    )
    return True


async def _on_confirm(query, user_id: int) -> None:
    flow = get_schedule_flow(user_id)
    if not flow or not flow.parsed_periods:
        await query.edit_message_text("Sesión expirada. Usa /db para empezar.")
        return

    async with get_db_session() as session:
        count = await save_schedule_periods(
            session,
            teacher_id=flow.teacher_id,
            day_of_week=flow.day_of_week,
            periods=flow.parsed_periods,
        )

    clear_schedule_flow(user_id)
    day_name = DAY_NAMES[flow.day_of_week]
    await query.edit_message_text(
        f"✅ *{count} período(s) guardados para {day_name}.*\n"
        "Repite con /db → Horario para registrar otros días.",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f"[schedule] user={user_id} day={flow.day_of_week} saved={count}")


# ── Keyboards (cacheados — son estáticos) ─────────────────────────────────────

_DAY_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton(name, callback_data=f"sch_day:{i}")]
        for i, name in enumerate(DAY_NAMES)
    ],
)

_CONFIRM_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("✅ Confirmar", callback_data="sch_confirm"),
            InlineKeyboardButton("❌ Cancelar", callback_data="sch_cancel"),
        ],
    ],
)
