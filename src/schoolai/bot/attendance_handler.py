"""Attendance skill handler.

Triggered by free text/audio — no command needed.
Flow: detect → extract names → ask grade if missing → resolve ambiguous names → save.
"""

from datetime import date

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.state import (
    PendingAttendance,
    clear_attendance,
    get_attendance,
    set_attendance,
)
from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.skills.attendance.constants import ABSENT, LATE, JUSTIFIED
from schoolai.skills.attendance.detector import extract_absences
from schoolai.skills.attendance.matcher import MatchResult, match_names
from schoolai.skills.attendance.service import save_absences
from schoolai.skills.homework.detector import extract_course
from schoolai.skills.homework.repository import find_grade
from schoolai.skills.utils.keyboards import grade_keyboard

from sqlalchemy import select


# ── Entry: called from dispatcher when attendance message detected ─────────────

async def start_attendance(update: Update, text: str) -> None:
    user_id = update.effective_user.id
    today = date.today()

    extracted = extract_absences(text)
    if not extracted:
        await update.message.reply_text(
            "Entendí que es asistencia pero no identifiqué nombres. "
            "Ejemplo: _Hoy faltaron Juan Pérez y María López del 3ro BT._",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    course_text = extract_course(text)
    grade = None
    if course_text:
        async with async_session() as session:
            grade = await find_grade(session, course_text)

    if not grade:
        # Ask for grade
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()

        state = PendingAttendance(
            step="await_grade",
            extracted=extracted,
            attendance_date=today,
        )
        set_attendance(user_id, state)

        names_preview = ", ".join(e["name"] for e in extracted[:5])
        if len(extracted) > 5:
            names_preview += f" y {len(extracted) - 5} más"

        await update.message.reply_text(
            f"Ausentes detectados: *{names_preview}*\n\n¿De qué curso?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "att_grade"),
        )
        return

    # Grade found in text — go straight to matching
    state = PendingAttendance(
        step="await_ambiguous",
        extracted=extracted,
        attendance_date=today,
        grade_id=grade.id,
        grade_name=grade.name,
    )
    set_attendance(user_id, state)
    await _run_matching(update, user_id, state)


# ── Callback dispatcher ───────────────────────────────────────────────────────

async def handle_attendance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data
    logger.info(f"[att_callback] user={user_id} data={data!r}")

    if data.startswith("att_grade:"):
        parts = data.split(":", 2)
        await _on_grade(query, user_id, int(parts[1]), parts[2])

    elif data.startswith("att_resolve:"):
        # att_resolve:{ambiguous_index}:{student_id}
        parts = data.split(":")
        await _on_resolve(query, user_id, int(parts[1]), int(parts[2]))

    elif data == "att_skip":
        await _on_skip(query, user_id)


# ── Step: grade selected ──────────────────────────────────────────────────────

async def _on_grade(query, user_id: int, grade_id: int, grade_name: str) -> None:
    state = get_attendance(user_id)
    if not state:
        await query.edit_message_text("Sesión expirada, vuelve a enviar el mensaje.")
        return

    state.grade_id = grade_id
    state.grade_name = grade_name
    state.step = "await_ambiguous"
    set_attendance(user_id, state)
    await _run_matching_on_query(query, user_id, state)


# ── Matching ──────────────────────────────────────────────────────────────────

async def _run_matching(update: Update, user_id: int, state: PendingAttendance) -> None:
    async with async_session() as session:
        results = await match_names(state.extracted, state.grade_id, session)
    await _process_results(update.message.reply_text, user_id, state, results)


async def _run_matching_on_query(query, user_id: int, state: PendingAttendance) -> None:
    async with async_session() as session:
        results = await match_names(state.extracted, state.grade_id, session)
    await _process_results(query.edit_message_text, user_id, state, results)


async def _process_results(reply_fn, user_id: int, state: PendingAttendance, results: list[MatchResult]) -> None:
    resolved = [r for r in results if r.resolved]
    ambiguous = [r for r in results if r.ambiguous]
    not_found = [r for r in results if r.not_found]

    # Add resolved to confirmed (include name for display)
    state.confirmed = [{"student_id": r.matched_id, "status": r.status, "name": r.matched_name} for r in resolved]
    state.ambiguous = ambiguous
    set_attendance(user_id, state)

    if not_found:
        names = ", ".join(r.raw_name for r in not_found)
        logger.warning(f"[attendance] not found in grade {state.grade_id}: {names}")

    if ambiguous:
        # Ask about first ambiguous
        await _ask_ambiguous(reply_fn, ambiguous[0], 0, not_found)
        return

    # All resolved — save
    await _save_and_reply(reply_fn, user_id, state, not_found)


# ── Ambiguity resolution ──────────────────────────────────────────────────────

async def _ask_ambiguous(reply_fn, match: MatchResult, idx: int, not_found: list) -> None:
    note = ""
    if not_found:
        note = f"\n_No encontré: {', '.join(r.raw_name for r in not_found)}_"

    buttons = [
        [InlineKeyboardButton(c["name"], callback_data=f"att_resolve:{idx}:{c['id']}")]
        for c in match.candidates
    ]
    buttons.append([InlineKeyboardButton("⏭ Omitir", callback_data="att_skip")])

    await reply_fn(
        f"Hay varios *{match.raw_name}* en el curso. ¿Cuál faltó?{note}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _on_resolve(query, user_id: int, idx: int, student_id: int) -> None:
    state = get_attendance(user_id)
    if not state or not state.ambiguous:
        await query.edit_message_text("Sesión expirada.")
        return

    resolved_match = state.ambiguous[idx]
    name = next((c["name"] for c in resolved_match.candidates if c["id"] == student_id), str(student_id))
    state.confirmed.append({"student_id": student_id, "status": resolved_match.status, "name": name})
    state.ambiguous = [r for i, r in enumerate(state.ambiguous) if i != idx]
    set_attendance(user_id, state)

    if state.ambiguous:
        next_match = state.ambiguous[0]
        await _ask_ambiguous(query.edit_message_text, next_match, 0, [])
    else:
        await _save_and_reply(query.edit_message_text, user_id, state, [])


async def _on_skip(query, user_id: int) -> None:
    state = get_attendance(user_id)
    if not state or not state.ambiguous:
        await query.edit_message_text("Sesión expirada.")
        return

    state.ambiguous = state.ambiguous[1:]
    set_attendance(user_id, state)

    if state.ambiguous:
        next_match = state.ambiguous[0]
        await _ask_ambiguous(query.edit_message_text, next_match, 0, [])
    else:
        await _save_and_reply(query.edit_message_text, user_id, state, [])


# ── Save ──────────────────────────────────────────────────────────────────────

async def _save_and_reply(reply_fn, user_id: int, state: PendingAttendance, not_found: list) -> None:
    if not state.confirmed:
        clear_attendance(user_id)
        await reply_fn("No se registró ninguna ausencia.")
        return

    student_ids = [c["student_id"] for c in state.confirmed]
    statuses = {c["student_id"]: c["status"] for c in state.confirmed}

    async with async_session() as session:
        result = await save_absences(student_ids, statuses, state.attendance_date, session)

    clear_attendance(user_id)

    absent    = [c for c in state.confirmed if c["status"] == ABSENT]
    late      = [c for c in state.confirmed if c["status"] == LATE]
    justified = [c for c in state.confirmed if c["status"] == JUSTIFIED]

    lines = [f"📋 *{state.grade_name} — {state.attendance_date.strftime('%d/%m/%Y')}*\n"]

    if absent:
        lines.append(f"❌ *Faltas ({len(absent)})*")
        lines.extend(f"  • {c['name']}" for c in absent)

    if late:
        lines.append(f"\n⏰ *Atrasos ({len(late)})*")
        lines.extend(f"  • {c['name']}" for c in late)

    if justified:
        lines.append(f"\n✅ *Justificados ({len(justified)})*")
        lines.extend(f"  • {c['name']}" for c in justified)

    if not_found:
        lines.append("\n⚠️ *No encontrados*")
        lines.extend(f"  • {r.raw_name}" for r in not_found)

    await reply_fn("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    logger.info(f"[attendance] user={user_id} saved {result.saved} records")
