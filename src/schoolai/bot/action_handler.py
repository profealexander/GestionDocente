"""Ejecuta la acción correspondiente al resultado de extracción LLM."""

from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode

from schoolai.db.connection import async_session
from schoolai.db.models.grade import Grade
from schoolai.skills.attendance.constants import ABSENT, LATE, JUSTIFIED
from schoolai.skills.attendance.matcher import match_names
from schoolai.skills.attendance.service import save_absences
from schoolai.skills.extractor.llm import _parse_date, _resolve_delivery
from schoolai.skills.extractor.schema import (
    AttendanceExtract,
    ExtractionResult,
    HomeworkExtract,
    HomeworkReportExtract,
    QueryExtract,
)
from schoolai.skills.homework.repository import (
    find_grade,
    find_subject,
    save_homework,
    find_homework_by_ref,
    save_non_completers,
    count_students_in_grade,
)
from schoolai.skills.utils.keyboards import grade_keyboard

# Caché ligero: datos parciales esperando que el usuario elija curso
# {user_id: ExtractionResult} — NO bloquea mensajes nuevos
_pending_cache: dict[int, ExtractionResult] = {}

STATUS_MAP = {
    "absent": ABSENT,
    "late": LATE,
    "justified": JUSTIFIED,
}


def store_pending(user_id: int, result: ExtractionResult) -> None:
    _pending_cache[user_id] = result


def pop_pending(user_id: int) -> ExtractionResult | None:
    return _pending_cache.pop(user_id, None)


async def handle_extraction(update: Update, user_id: int, result: ExtractionResult) -> None:
    """Punto de entrada principal. Actúa según el resultado del extractor."""
    intent = result.intent
    data = result.data

    if intent == "attendance":
        await _handle_attendance(update, user_id, result, data)
    elif intent == "homework":
        await _handle_homework(update, user_id, result, data)
    elif intent == "homework_report":
        await _handle_homework_report(update, user_id, result, data)
    elif intent == "query":
        await _handle_query(update, user_id, result, data)
    else:
        # chat — manejado por el caller
        pass


# ── Attendance ────────────────────────────────────────────────────────────────

async def _handle_attendance(update, user_id: int, result: ExtractionResult, data: AttendanceExtract) -> None:
    if not data.names:
        await update.message.reply_text(
            "Entendí que es asistencia pero no identifiqué nombres.\n"
            "_Ejemplo: Hoy faltaron Juan Pérez y María López del 3ro BT._",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
        names_preview = ", ".join(data.names[:3])
        if len(data.names) > 3:
            names_preview += f" y {len(data.names) - 3} más"
        await update.message.reply_text(
            f"Ausentes: *{names_preview}*\n\n¿De qué curso?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return

    await _save_attendance(update.message.reply_text, user_id, data)


async def _save_attendance(reply_fn, user_id: int, data: AttendanceExtract) -> None:
    attendance_date = _parse_date(data.date)
    status = STATUS_MAP.get(data.status, ABSENT)
    extracted = [{"name": n, "status": status} for n in data.names]

    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        results = await match_names(extracted, grade.id, session)

    resolved = [r for r in results if r.resolved]
    ambiguous = [r for r in results if r.ambiguous]
    not_found = [r for r in results if r.not_found]

    # Guardar resueltos directo
    if resolved:
        student_ids = [r.matched_id for r in resolved]
        statuses = {r.matched_id: r.status for r in resolved}
        async with async_session() as session:
            await save_absences(student_ids, statuses, attendance_date, session)

    lines = [f"📋 *{data.course} — {attendance_date.strftime('%d/%m/%Y')}*\n"]

    status_label = {"absent": "Faltas", "late": "Atrasos", "justified": "Justificados"}.get(data.status, "Faltas")
    if resolved:
        lines.append(f"✅ *{status_label} registrados ({len(resolved)})*")
        lines.extend(f"  • {r.matched_name}" for r in resolved)

    if ambiguous:
        lines.append(f"\n⚠️ *Nombres ambiguos (no registrados)*")
        lines.extend(f"  • {r.raw_name}" for r in ambiguous)

    if not_found:
        lines.append(f"\n❌ *No encontrados*")
        lines.extend(f"  • {r.raw_name}" for r in not_found)

    await reply_fn("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    logger.info(f"[action] attendance user={user_id} saved={len(resolved)}")


# ── Homework ──────────────────────────────────────────────────────────────────

async def _handle_homework(update, user_id: int, result: ExtractionResult, data: HomeworkExtract) -> None:
    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
        await update.message.reply_text(
            f"Tarea: *{data.description[:60]}*\n\n¿Para qué curso?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return

    await _save_homework(update.message.reply_text, user_id, data)


async def _save_homework(reply_fn, user_id: int, data: HomeworkExtract) -> None:
    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        subject = await find_subject(session, data.subject) if data.subject else None
        delivery = _resolve_delivery(data.delivery_date)

        record = await save_homework(
            session,
            homework=data.description,
            grade_id=grade.id,
            subject_id=subject.id if subject else None,
            delivery_date=delivery,
        )

    delivery_str = record.delivery_date.strftime("%d/%m/%Y") if record.delivery_date else "no especificada"
    subject_str = subject.name if subject else "sin materia"
    await reply_fn(
        f"✅ Tarea #{record.sequence_num} registrada\n"
        f"{subject_str} | {grade.name} | Trimestre {record.trimester_num}\n"
        f"Entrega: {delivery_str}",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f"[action] homework user={user_id} id={record.id}")


# ── Query ─────────────────────────────────────────────────────────────────────

async def _handle_query(update, user_id: int, result: ExtractionResult, data: QueryExtract) -> None:
    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
        await update.message.reply_text(
            "¿De qué curso quieres la consulta?",
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return

    # Reusar query_handler existente
    from schoolai.bot.query_handler import _run_query
    from schoolai.skills.query.detector import QueryIntent, get_current_trimester

    today = date.today()
    period = data.period

    if period == "today":
        start = end = today
        period_type = "day"
    elif period == "yesterday":
        start = end = today - timedelta(days=1)
        period_type = "day"
    elif period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=4)
        period_type = "week"
    elif period == "last_week":
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=4)
        period_type = "week"
    elif period == "month":
        start = today.replace(day=1)
        end = today
        period_type = "month"
    elif period == "last_month":
        first = today.replace(day=1)
        end = first - timedelta(days=1)
        start = end.replace(day=1)
        period_type = "month"
    else:  # trimester
        num, start, end = get_current_trimester()
        period_type = "trimester"

    intent = QueryIntent(
        type=data.query_type,
        period=period_type,
        period_start=start,
        period_end=end,
    )

    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await update.message.reply_text(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

    await _run_query(update.message.reply_text, user_id, intent, grade.id)


# ── Homework Report ───────────────────────────────────────────────────────────

async def _handle_homework_report(update, user_id: int, result: ExtractionResult, data: HomeworkReportExtract) -> None:
    if not data.course:
        store_pending(user_id, result)
        async with async_session() as session:
            grades = (await session.execute(select(Grade).order_by(Grade.sort_order))).scalars().all()
        await update.message.reply_text(
            "¿De qué curso es el reporte?",
            reply_markup=grade_keyboard(grades, "act_grade"),
        )
        return
    await _save_homework_report(update.message.reply_text, user_id, data)


async def _save_homework_report(reply_fn, user_id: int, data: HomeworkReportExtract) -> None:
    async with async_session() as session:
        grade = await find_grade(session, data.course)
        if not grade:
            await reply_fn(f"No encontré el curso *{data.course}*.", parse_mode=ParseMode.MARKDOWN)
            return

        subject = await find_subject(session, data.subject) if data.subject else None

        homework = await find_homework_by_ref(
            session,
            sequence_num=data.homework_ref or 1,
            grade_id=grade.id,
            subject_id=subject.id if subject else None,
        )

        if not homework:
            ref_str = f"#{data.homework_ref}" if data.homework_ref else "más reciente"
            subj_str = subject.name if subject else "sin materia"
            await reply_fn(
                f"No encontré la tarea {ref_str} de *{subj_str}* para *{grade.name}*.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # Match names against students in the grade
        extracted = [{"name": n, "status": data.status} for n in data.names]
        results = await match_names(extracted, grade.id, session)

        resolved = [r for r in results if r.resolved]
        not_found = [r for r in results if r.not_found]

        # Save non-completers
        if resolved:
            await save_non_completers(
                session,
                homework_id=homework.id,
                student_ids=[r.matched_id for r in resolved],
                status=data.status,
            )

        total = await count_students_in_grade(session, grade.id)
        missing_count = len(resolved)
        completed_count = max(0, total - missing_count)

        status_label = {"missing": "No cumplieron", "late": "Entregaron tarde", "partial": "Entrega parcial"}.get(data.status, "No cumplieron")
        subject_name = subject.name if subject else "sin materia"

        lines = [
            f"📋 *Tarea #{homework.sequence_num} — {subject_name} / {grade.name}*\n",
            f"✗ *{status_label} ({missing_count}):*",
        ]
        lines.extend(f"  • {r.matched_name}" for r in resolved)
        lines.append(f"\n✓ Cumplieron: *{completed_count} de {total}*")

        if not_found:
            lines.append(f"\n⚠️ No encontrados: {', '.join(r.raw_name for r in not_found)}")

        await reply_fn("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        logger.info(f"[action] homework_report user={user_id} hw={homework.id} missing={missing_count}")


# ── Callback: usuario eligió curso ────────────────────────────────────────────

async def handle_act_callback(update, context) -> None:
    """Maneja selección de curso cuando el extractor no lo detectó."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data  # "act_grade:{id}:{name}"

    parts = data.split(":", 2)
    grade_name = parts[2] if len(parts) > 2 else parts[1]

    result = pop_pending(user_id)
    if not result:
        await query.edit_message_text("Sesión expirada. Vuelve a enviar el mensaje.")
        return

    # Completar con el curso seleccionado
    if result.intent == "attendance":
        result.data.course = grade_name
        result.data.complete = True
        await _save_attendance(query.edit_message_text, user_id, result.data)
    elif result.intent == "homework":
        result.data.course = grade_name
        result.data.complete = True
        await _save_homework(query.edit_message_text, user_id, result.data)
    elif result.intent == "homework_report":
        result.data.course = grade_name
        result.data.complete = True
        await _save_homework_report(query.edit_message_text, user_id, result.data)
    elif result.intent == "query":
        result.data.course = grade_name
        result.data.complete = True
        # Reconstruir con reply_text porque edit_message_text no funciona igual con _run_query
        from schoolai.bot.query_handler import _run_query
        from schoolai.skills.query.detector import QueryIntent, get_current_trimester
        from schoolai.skills.homework.repository import find_grade as _find_grade

        today = date.today()
        period = result.data.period
        if period == "today":
            start = end = today
            period_type = "day"
        elif period == "yesterday":
            start = end = today - timedelta(days=1)
            period_type = "day"
        elif period in ("week", "last_week"):
            offset = -7 if period == "last_week" else 0
            start = today - timedelta(days=today.weekday()) + timedelta(days=offset)
            end = start + timedelta(days=4)
            period_type = "week"
        elif period in ("month", "last_month"):
            if period == "month":
                start = today.replace(day=1)
                end = today
            else:
                first = today.replace(day=1)
                end = first - timedelta(days=1)
                start = end.replace(day=1)
            period_type = "month"
        else:
            num, start, end = get_current_trimester()
            period_type = "trimester"

        intent_obj = QueryIntent(type=result.data.query_type, period=period_type, period_start=start, period_end=end)
        async with async_session() as session:
            grade = await _find_grade(session, grade_name)
        if grade:
            await _run_query(query.edit_message_text, user_id, intent_obj, grade.id)
        else:
            await query.edit_message_text(f"No encontré el curso {grade_name}.")
