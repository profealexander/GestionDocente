"""Handlers de tareas: _handle_homework y _save_homework."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.bot.action.cache import store_pending
from schoolai.bot.state import (
    PendingConfirm,
    clear_course_context,
    get_course_context,
    get_jornada_context,
    set_pending_confirm,
)
from schoolai.constants import TRUNCATE_SHORT_PREVIEW
from schoolai.db.connection import get_db_session
from schoolai.db.models.grade import Grade
from schoolai.skills.homework.repository import (
    find_grade,
    find_subject,
    get_teacher_subject_ids,
    save_homework,
)
from schoolai.skills.utils.keyboards import grade_keyboard
from schoolai.skills.utils.schema import ExtractionResult, HomeworkExtract


async def _handle_homework(
    update,
    user_id: int,
    result: ExtractionResult,
    data: HomeworkExtract,
) -> None:
    if not data.course or not data.subject:
        grade_id, grade_name, subject_id, subject_name = get_jornada_context(user_id)
        if grade_name and not data.course:
            data.course = grade_name
        if subject_name and not data.subject:
            data.subject = subject_name
        if data.course and data.subject:
            data.complete = True
            result.via_llm = False

    if not data.course:
        ctx = get_course_context(user_id)
        if ctx and ctx.pending_intent == "homework":
            data.course = ctx.grade_name
            data.complete = True
            clear_course_context(user_id)

    if not data.course:
        store_pending(user_id, result)
        async with get_db_session() as session:
            grades = (
                (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
            )
        await update.message.reply_text(
            f"Tarea: *{data.description[:TRUNCATE_SHORT_PREVIEW]}*\n\n¿Para qué curso?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return

    if not data.subject and not data.subjects:
        await update.message.reply_text(
            f"⚠️ No se puede registrar una tarea sin materia.\n"
            f"Indica la materia en el mensaje, por ejemplo:\n"
            f"_Tarea de Matemáticas para {data.course}: {data.description[:40]}_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    from schoolai.config import settings

    subjects_display = ", ".join(data.subjects) if data.subjects else data.subject
    if settings.supervised_mode:
        desc_preview = data.description[:TRUNCATE_SHORT_PREVIEW]
        set_pending_confirm(
            user_id,
            PendingConfirm(
                chat_id=update.message.chat_id,
                intent="homework",
                summary=f"*{data.course}* — {subjects_display}\n_{desc_preview}_",
                data=data,
            ),
        )
        await update.message.reply_text(
            f"🤖 *Extracción automática — ¿es correcto?*\n\n"
            f"Curso: *{data.course}* | Materia: *{subjects_display}*\n"
            f"_{desc_preview}_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Confirmar", callback_data="act_confirm:yes"),
                        InlineKeyboardButton("❌ Cancelar", callback_data="act_confirm:no"),
                    ],
                ],
            ),
        )
        return

    await _save_homework(update.message.reply_text, user_id, data)


async def _save_homework(reply_fn, user_id: int, data: HomeworkExtract) -> None:
    from sqlalchemy import select as _select

    from schoolai.db.models.teacher import Teacher

    subjects_list = data.subjects or ([data.subject] if data.subject else [])
    if not subjects_list:
        await reply_fn("⚠️ No se puede registrar una tarea sin materia.")
        return

    async with get_db_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        from schoolai.skills.utils.dates import resolve_delivery as _resolve_delivery

        delivery = _resolve_delivery(data.delivery_date)

        from schoolai.bot.state import get_jornada as _get_jornada

        jornada = _get_jornada(user_id)
        teacher_id = jornada.teacher_id if jornada else None
        if not teacher_id:
            teacher_id = (
                await session.execute(
                    _select(Teacher.id).where(
                        Teacher.telegram_id == user_id,
                        Teacher.is_active.is_(True),
                    ),
                )
            ).scalar_one_or_none()

        allowed_subject_ids: list[int] | None = None
        if teacher_id:
            ids = await get_teacher_subject_ids(session, teacher_id, grade.id)
            if ids:
                allowed_subject_ids = ids

        records: list[tuple] = []
        skipped: list[str] = []
        for subj_name in subjects_list:
            subj_obj = (
                await find_subject(session, subj_name)
                if subj_name and subj_name != "Asignación"
                else None
            )
            if (
                allowed_subject_ids is not None
                and subj_obj is not None
                and subj_obj.id not in allowed_subject_ids
            ):
                skipped.append(subj_obj.name)
                continue
            record = await save_homework(
                session,
                homework=data.description,
                grade_id=grade.id,
                subject_id=subj_obj.id if subj_obj else None,
                delivery_date=delivery,
                teacher_id=teacher_id,
            )
            records.append((record, subj_obj, subj_name))

    if not records and teacher_id and allowed_subject_ids:
        from schoolai.skills.homework.repository import get_teacher_subjects
        from schoolai.skills.utils.dates import resolve_delivery as _resolve_delivery

        async with get_db_session() as session:
            grade = await find_grade(session, data.course)
            delivery = _resolve_delivery(data.delivery_date)
            teacher_subjects = await get_teacher_subjects(session, teacher_id, grade.id)
            for subj_obj in teacher_subjects:
                record = await save_homework(
                    session,
                    homework=data.description,
                    grade_id=grade.id,
                    subject_id=subj_obj.id,
                    delivery_date=delivery,
                    teacher_id=teacher_id,
                )
                records.append((record, subj_obj, subj_obj.name))

    if not records:
        await reply_fn(
            "No pude registrar la tarea. Verifica que tengas materias asignadas en el horario.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    delivery_str = (
        records[0][0].delivery_date.strftime("%d/%m/%Y")
        if records[0][0].delivery_date
        else "no especificada"
    )

    if len(records) == 1:
        record, subj_obj, subj_name = records[0]
        subject_str = subj_obj.name if subj_obj else "sin materia"
        msg = (
            f"✅ Tarea #{record.sequence_num} registrada\n"
            f"{subject_str} | {grade.name} | Trimestre {record.trimester_num}\n"
            f"Entrega: {delivery_str}"
        )
        if skipped:
            msg += f"\n⚠️ Omitidas (no son tus materias): {', '.join(skipped)}"
        await reply_fn(msg, parse_mode=ParseMode.MARKDOWN)
        logger.info(f"[action] homework user={user_id} id={record.id}")
    else:
        lines = [
            f"✅ *{len(records)} tareas registradas* — "
            f"{grade.name} | Trimestre {records[0][0].trimester_num}",
        ]
        for record, subj_obj, subj_name in records:
            subj_label = subj_obj.name if subj_obj else subj_name
            lines.append(f"  • Tarea #{record.sequence_num} — {subj_label}")
        lines.append(f"Entrega: {delivery_str}")
        if skipped:
            lines.append(f"⚠️ Omitidas (no son tus materias): {', '.join(skipped)}")
        await reply_fn("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        logger.info(f"[action] homework user={user_id} ids={[r[0].id for r in records]}")
