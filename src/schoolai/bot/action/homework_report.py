"""Handlers de reporte de cumplimiento: _handle_homework_report y _save_homework_report."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from telegram.constants import ParseMode

from schoolai.bot.action._widgets import _HW_STATUS_LABELS, _sel_keyboard
from schoolai.bot.action.cache import store_pending
from schoolai.bot.action.notify import _send_notify_prompt
from schoolai.bot.state import (
    PendingCourseContext,
    PendingSelection,
    clear_course_context,
    get_course_context,
    get_jornada_context,
    set_course_context,
    set_selection,
)
from schoolai.db.connection import get_db_session
from schoolai.db.models.grade import Grade
from schoolai.db.models.homework import Homework
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.homework.repository import (
    count_students_in_grade,
    find_grade,
    find_homework_by_ref,
    find_subject,
    list_open,
    save_non_completers,
)
from schoolai.skills.utils.courses import course_abbrev_map
from schoolai.skills.utils.keyboards import grade_keyboard
from schoolai.skills.utils.schema import ExtractionResult, HomeworkReportExtract


async def _handle_homework_report(
    update,
    user_id: int,
    result: ExtractionResult,
    data: HomeworkReportExtract,
) -> None:
    if not data.course:
        grade_id, grade_name, _, _ = get_jornada_context(user_id)
        if grade_name:
            data.course = grade_name
            data.complete = True
            result.via_llm = False

    if not data.course:
        ctx = get_course_context(user_id)
        if ctx and ctx.pending_intent == "homework_report":
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
            "¿De qué curso es el reporte?",
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return
    await _save_homework_report(update.message.reply_text, user_id, data, update.message.chat_id)


async def _save_homework_report(
    reply_fn,
    user_id: int,
    data: HomeworkReportExtract,
    chat_id: int = 0,
) -> None:

    async with get_db_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        subject = await find_subject(session, data.subject) if data.subject else None

        extracted = [{"name": n, "status": data.status} for n in data.names]
        name_results = await match_names(extracted, grade.id, session)
        resolved_names = [r for r in name_results if r.resolved]
        ambiguous_names = [r for r in name_results if r.ambiguous]
        not_found_names = [r for r in name_results if r.not_found]

        hw_resolved = None
        hw_list = None
        hw_options = None

        if data.homework_ref is not None:
            hw_resolved = await find_homework_by_ref(
                session,
                sequence_num=data.homework_ref,
                grade_id=grade.id,
                subject_id=subject.id if subject else None,
            )
            if hw_resolved is None:
                open_tasks = await list_open(session, grade.id)
                if not open_tasks:
                    await reply_fn(
                        f"No hay tareas abiertas para *{grade.name}*.",
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return
                hw_options = [
                    {
                        "id": t.id,
                        "subject": t.subject.name if t.subject else "Sin materia",
                        "date": t.delivery_date.strftime("%d/%m") if t.delivery_date else "",
                    }
                    for t in open_tasks
                ]

        elif subject:
            stmt = (
                select(Homework)
                .where(
                    Homework.grade_id == grade.id,
                    Homework.subject_id == subject.id,
                    Homework.is_open.is_(True),
                )
                .order_by(Homework.submission_date.desc())
                .limit(1)
            )
            hw_resolved = (await session.execute(stmt)).scalars().first()
            if not hw_resolved:
                await reply_fn(
                    f"No hay tareas abiertas de *{subject.name}* para *{grade.name}*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

        else:
            hw_list = await list_open(session, grade.id)
            if not hw_list:
                await reply_fn(
                    f"No hay tareas abiertas para *{grade.name}*.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

        if ambiguous_names:
            queue = [{"raw_name": r.raw_name, "candidates": r.candidates} for r in ambiguous_names]
            first = queue[0]
            first_options = [
                {"label": c.get("short", c["name"]).title(), "value": str(c["id"])}
                for c in first["candidates"]
            ]
            payload: dict = {
                "queue": queue,
                "resolved_ids": [r.matched_id for r in resolved_names],
                "resolved_names": [r.matched_name for r in resolved_names],
                "not_found_names": [r.raw_name for r in not_found_names],
                "status": data.status,
                "grade_id": grade.id,
                "chat_id": chat_id,
                "hw_id": hw_resolved.id if hw_resolved else None,
                "hw_ids": [h.id for h in hw_list] if hw_list else None,
                "hw_options": hw_options,
            }
            pending = PendingSelection(
                chat_id=chat_id,
                prompt=(
                    f"⚠️ *¿A cuál _{first['raw_name']}_ te refieres?*\n"
                    "_Toca un botón o escribe el número:_"
                ),
                options=first_options,
                action="hw_student",
                payload=payload,
            )
            set_selection(user_id, pending)
            await reply_fn(
                pending.prompt,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_sel_keyboard(first_options),
            )
            return

        student_ids = [r.matched_id for r in resolved_names]
        student_names = [r.matched_name for r in resolved_names]
        not_found_strs = [r.raw_name for r in not_found_names]

        if hw_options is not None:
            task_options = [
                {
                    "label": opt["subject"] + (f" — {opt['date']}" if opt.get("date") else ""),
                    "value": str(opt["id"]),
                }
                for opt in hw_options
            ]
            pending = PendingSelection(
                chat_id=chat_id,
                prompt=(
                    f"⚠️ No encontré la tarea *#{data.homework_ref}* en *{grade.name}*.\n"
                    "¿A cuál te refieres?\n_Toca un botón o escribe el número:_"
                ),
                options=task_options,
                action="hw_task",
                payload={
                    "student_ids": student_ids,
                    "student_names": student_names,
                    "not_found_names": not_found_strs,
                    "status": data.status,
                    "grade_id": grade.id,
                    "chat_id": chat_id,
                },
            )
            set_selection(user_id, pending)
            await reply_fn(
                pending.prompt,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_sel_keyboard(task_options),
            )
            return

        homeworks = [hw_resolved] if hw_resolved else hw_list

        if student_ids:
            for hw in homeworks:
                await save_non_completers(session, hw.id, student_ids, data.status, commit=False)
            await session.commit()

        status_label = _HW_STATUS_LABELS.get(data.status, "No entregaron")

        total = await count_students_in_grade(session, grade.id)
        missing = len(student_ids)

        if len(homeworks) == 1:
            hw = homeworks[0]
            subj_name = hw.subject.name if hw.subject else "sin materia"
            lines = [
                f"📊 *CUMPLIMIENTO — Tarea #{hw.sequence_num}*",
                f"_{subj_name} / {grade.name}_\n",
            ]
        else:
            tareas_str = ", ".join(f"#{hw.sequence_num}" for hw in homeworks)
            lines = [
                f"📊 *CUMPLIMIENTO — Tareas {tareas_str}*",
                f"_{grade.name}_ (todas abiertas)\n",
            ]

        lines.append(f"✗ *{status_label} ({missing}):*")
        lines.extend(f"  • {r.matched_name}" for r in resolved_names)
        lines.append(f"\n✓ Cumplieron: *{max(0, total - missing)} de {total}*")

        if not_found_strs:
            lines.append(f"\n⚠️ No encontrados: {', '.join(not_found_strs)}")

        await reply_fn("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        if len(homeworks) == 1 and student_ids:
            await _send_notify_prompt(
                reply_fn,
                user_id,
                homeworks[0],
                student_ids,
                [r.matched_name for r in resolved_names],
            )

        if user_id:
            abbrev = next((k for k, v in course_abbrev_map.items() if v == grade.id), "")
            set_course_context(
                user_id,
                PendingCourseContext(
                    course_abbrev=abbrev,
                    grade_id=grade.id,
                    grade_name=grade.name,
                    pending_intent="homework_report",
                ),
            )

        logger.info(
            f"[action] homework_report user={user_id} grade={grade.id} "
            f"tasks={len(homeworks)} missing={missing}",
        )
