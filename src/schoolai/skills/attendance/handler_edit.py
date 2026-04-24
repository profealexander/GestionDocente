"""Handler de edición de asistencia.

Flow:
  handle_att_edit → grade picker (si no hay curso) → lista de ausentes
  att_edit_grade → lista de ausentes del día
  att_edit_pick  → opciones de cambio de estado
  att_edit_set   → actualiza estado (F/AT/J)
  att_edit_del   → elimina registro
"""

from __future__ import annotations

from datetime import date

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.db.connection import get_db_session
from schoolai.db.models.attendance import Attendance
from schoolai.db.models.person import Person
from schoolai.db.models.student import Student
from schoolai.skills.attendance.constants import ABSENT, JUSTIFIED, LATE

_STATUS_ICON = {ABSENT: "❌", LATE: "⏰", JUSTIFIED: "✅"}
_STATUS_LABEL = {ABSENT: "Falta", LATE: "Atraso", JUSTIFIED: "Justificado"}
_STATUS_CHOICES = [
    (ABSENT, "❌ Falta"),
    (LATE, "⏰ Atraso"),
    (JUSTIFIED, "✅ Justificado"),
]


# ── DB helpers ─────────────────────────────────────────────────────────────────


async def _load_records(session, grade_id: int, att_date: date) -> list[tuple]:
    """Returns list of (att_id, student_id, 'Apellido Nombre', status) sorted by last name."""
    stmt = (
        select(
            Attendance.id,
            Attendance.student_id,
            Attendance.status,
            Person.first_name,
            Person.last_name,
        )
        .join(Student, Attendance.student_id == Student.id)
        .join(Person, Student.person_id == Person.id)
        .where(
            Student.grade_id == grade_id,
            Attendance.date == att_date,
        )
        .order_by(Person.last_name, Person.first_name)
    )
    rows = (await session.execute(stmt)).all()
    return [(r[0], r[1], f"{r[4]} {r[3]}", r[2]) for r in rows]


async def _get_student_name(session, student_id: int) -> str:
    row = (
        await session.execute(
            select(Person.first_name, Person.last_name)
            .join(Student, Person.id == Student.person_id)
            .where(Student.id == student_id),
        )
    ).first()
    return f"{row[1]} {row[0]}" if row else f"Estudiante #{student_id}"


# ── Keyboard builders ──────────────────────────────────────────────────────────


def _list_keyboard(records: list[tuple]) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                f"{_STATUS_ICON.get(status, '?')} {name}",
                callback_data=f"att_edit_pick:{att_id}",
            ),
        ]
        for att_id, _, name, status in records
    ]
    return InlineKeyboardMarkup(buttons)


def _status_keyboard(att_id: int, current_status: str) -> InlineKeyboardMarkup:
    change_row = [
        InlineKeyboardButton(label, callback_data=f"att_edit_set:{att_id}:{s}")
        for s, label in _STATUS_CHOICES
        if s != current_status
    ]
    del_row = [InlineKeyboardButton("🗑 Eliminar registro", callback_data=f"att_edit_del:{att_id}")]
    return InlineKeyboardMarkup([change_row, del_row])


# ── Entry point ────────────────────────────────────────────────────────────────


async def handle_att_edit(
    update,
    user_id: int,
    course: str | None,
    att_date: date | None,
) -> None:
    from schoolai.db.models.grade import Grade
    from schoolai.skills.homework.repository import find_grade

    att_date = att_date or date.today()

    if course:
        async with get_db_session() as session:
            grade = await find_grade(session, course)
        if not grade:
            await update.message.reply_text(f"Curso '{course}' no encontrado.")
            return
        await _show_list(update.message.reply_text, grade.id, grade.name, att_date)
    else:
        async with get_db_session() as session:
            grades = (
                await session.execute(select(Grade).order_by(Grade.sort_order))
            ).scalars().all()

        date_str = att_date.strftime("%d/%m/%Y")
        date_iso = att_date.isoformat()
        buttons: list[list] = []
        row: list = []
        for g in grades:
            row.append(
                InlineKeyboardButton(
                    g.name, callback_data=f"att_edit_grade:{g.id}:{date_iso}",
                ),
            )
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        await update.message.reply_text(
            f"¿De qué curso quieres editar la asistencia del *{date_str}*?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )


async def _show_list(reply_fn, grade_id: int, grade_name: str, att_date: date) -> None:
    async with get_db_session() as session:
        records = await _load_records(session, grade_id, att_date)

    date_str = att_date.strftime("%d/%m/%Y")
    if not records:
        await reply_fn(
            f"Sin ausencias registradas en *{grade_name}* el {date_str}.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await reply_fn(
        f"Asistencia *{grade_name}* — {date_str}\n"
        "Toca un estudiante para cambiar su estado:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_list_keyboard(records),
    )


# ── Callbacks ──────────────────────────────────────────────────────────────────


async def handle_att_edit_grade_callback(update, context) -> None:
    """att_edit_grade:{grade_id}:{date_iso}"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    grade_id = int(parts[1])
    att_date = date.fromisoformat(parts[2])

    from schoolai.db.models.grade import Grade

    async with get_db_session() as session:
        grade = await session.get(Grade, grade_id)

    if not grade:
        await query.edit_message_text("Curso no encontrado.")
        return

    date_str = att_date.strftime("%d/%m/%Y")
    async with get_db_session() as session:
        records = await _load_records(session, grade_id, att_date)

    if not records:
        await query.edit_message_text(
            f"Sin ausencias registradas en *{grade.name}* el {date_str}.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await query.edit_message_text(
        f"Asistencia *{grade.name}* — {date_str}\n"
        "Toca un estudiante para cambiar su estado:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_list_keyboard(records),
    )


async def handle_att_edit_pick_callback(update, context) -> None:
    """att_edit_pick:{att_id}"""
    query = update.callback_query
    await query.answer()

    att_id = int(query.data.split(":")[1])

    async with get_db_session() as session:
        att = await session.get(Attendance, att_id)
        if not att:
            await query.edit_message_text("Registro no encontrado.")
            return
        name = await _get_student_name(session, att.student_id)
        status = att.status
        att_date = att.date

    icon = _STATUS_ICON.get(status, "?")
    label = _STATUS_LABEL.get(status, status)
    date_str = att_date.strftime("%d/%m/%Y")

    await query.edit_message_text(
        f"{icon} *{name}* — {date_str}\nEstado actual: *{label}*\n\n¿Qué deseas hacer?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_status_keyboard(att_id, status),
    )


async def handle_att_edit_set_callback(update, context) -> None:
    """att_edit_set:{att_id}:{status}"""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    att_id, new_status = int(parts[1]), parts[2]

    async with get_db_session() as session:
        att = await session.get(Attendance, att_id)
        if not att:
            await query.edit_message_text("Registro no encontrado.")
            return
        att.status = new_status
        await session.commit()
        name = await _get_student_name(session, att.student_id)

    icon = _STATUS_ICON.get(new_status, "?")
    label = _STATUS_LABEL.get(new_status, new_status)
    logger.info(f"[attendance_edit] att_id={att_id} → {new_status}")

    await query.edit_message_text(
        f"✅ Actualizado: *{name}* → {icon} {label}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_att_edit_del_callback(update, context) -> None:
    """att_edit_del:{att_id}"""
    query = update.callback_query
    await query.answer()

    att_id = int(query.data.split(":")[1])

    async with get_db_session() as session:
        att = await session.get(Attendance, att_id)
        if not att:
            await query.edit_message_text("Registro no encontrado.")
            return
        name = await _get_student_name(session, att.student_id)
        await session.delete(att)
        await session.commit()

    logger.info(f"[attendance_edit] deleted att_id={att_id}")
    await query.edit_message_text(
        f"✅ Eliminado: *{name}* ya no figura como ausente ese día.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Auto-register ──────────────────────────────────────────────────────────────

from schoolai.bot.callback_router import callback_router  # noqa: E402

callback_router.register("att_edit_grade:")(handle_att_edit_grade_callback)
callback_router.register("att_edit_pick:")(handle_att_edit_pick_callback)
callback_router.register("att_edit_set:")(handle_att_edit_set_callback)
callback_router.register("att_edit_del:")(handle_att_edit_del_callback)
