"""Registro y consulta de ausencias del docente (teacher_absences)."""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import desc, select

from schoolai.db.connection import get_db_session
from schoolai.db.models.teacher_absence import TeacherAbsence
from schoolai.skills.db.schedule_service import get_teacher_by_telegram

if TYPE_CHECKING:
    from schoolai.bot.state import JornadaSession


# ── Repositorio ───────────────────────────────────────────────────────────────

async def save_teacher_absences(jornada: JornadaSession) -> None:
    """Persiste las ausencias del docente en teacher_absences."""
    if not jornada.absences:
        return

    today = date.today()
    period_map = {p["period_num"]: p for p in jornada.periods}
    scope = "day" if len(jornada.absences) == len(jornada.periods) else "period"

    async with get_db_session() as session:
        for absence in jornada.absences:
            p = period_map.get(absence["period_num"], {})
            session.add(TeacherAbsence(
                teacher_id=jornada.teacher_id,
                date=today,
                scope=scope,
                period_num=absence.get("period_num"),
                grade_id=p.get("grade_id"),
                subject_name=absence.get("subject_name"),
                period_start=p.get("start_time"),
                period_end=p.get("end_time"),
                reason=absence.get("reason", "other"),
                reason_label=absence.get("reason_label", ""),
            ))
        await session.commit()


async def list_absences(teacher_id: int, limit: int = 10) -> list[TeacherAbsence]:
    """Retorna las últimas N ausencias del docente ordenadas por fecha descendente."""
    async with get_db_session() as session:
        rows = (await session.execute(
            select(TeacherAbsence)
            .where(TeacherAbsence.teacher_id == teacher_id)
            .order_by(desc(TeacherAbsence.date), TeacherAbsence.period_num)
            .limit(limit)
        )).scalars().all()
    return list(rows)


def format_absences(rows: list[TeacherAbsence]) -> str:
    """Formatea la lista de ausencias como HTML para Telegram."""
    _SCOPE = {"day": "Jornada completa", "period": "Período"}
    lines = [f"📋 <b>Tus ausencias</b> (últimas {len(rows)}):\n"]
    current_date = None
    for r in rows:
        if r.date != current_date:
            current_date = r.date
            lines.append(f"\n📅 <b>{r.date.strftime('%d/%m/%Y')}</b>")
        scope_label = _SCOPE.get(r.scope, r.scope)
        period_info = f" P{r.period_num}" if r.period_num and r.scope == "period" else ""
        subject_info = f" · {r.subject_name}" if r.subject_name else ""
        lines.append(f"  • {scope_label}{period_info}{subject_info}")
        lines.append(f"    <i>{r.reason_label}</i>")
    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_ausencias_command(update, context) -> None:
    """/ausencias [N] — muestra las últimas N ausencias del docente (default 10)."""
    user_id = update.effective_user.id
    args = context.args or []
    try:
        limit = max(1, min(int(args[0]), 50)) if args else 10
    except ValueError:
        limit = 10

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await update.message.reply_text("No tienes un perfil de docente vinculado.")
            return

    rows = await list_absences(teacher.id, limit)
    if not rows:
        await update.message.reply_text("✅ No tienes ausencias registradas.")
        return

    text = format_absences(rows)
    if len(rows) == limit:
        text += f"\n\n<i>Escribe 'mis ausencias {limit * 2}' para ver más.</i>"
    await update.message.reply_text(text, parse_mode="HTML")


# ── Interceptor de lenguaje natural ──────────────────────────────────────────

_AUSENCIAS_RE = re.compile(
    r"\b(mis? ausencias?|ver ausencias?|ausencias? m[ií]as?|"
    r"cu[aá]ntas? (veces?|d[ií]as?) (falt[eé]|estuve ausente)|"
    r"falt[eé] (mucho|poco|\w+\s+veces?)?|"
    r"registro de (mis? )?ausencias?|"
    r"cu[aá]ndo falt[eé]|mis? inasistencias?)\b",
    re.IGNORECASE,
)

_LIMIT_RE = re.compile(r"\b(\d+)\b")


async def ausencias_interceptor(update, user_id: int) -> bool:
    """Detecta consultas de ausencias propias en lenguaje natural."""
    if not _AUSENCIAS_RE.search(update.message.text):
        return False

    m = _LIMIT_RE.search(update.message.text)
    limit = max(1, min(int(m.group(1)), 50)) if m else 10

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            return False

    rows = await list_absences(teacher.id, limit)
    if not rows:
        await update.message.reply_text("✅ No tienes ausencias registradas.")
        return True

    text = format_absences(rows)
    if len(rows) == limit:
        text += f"\n\n<i>Escribe 'mis ausencias {limit * 2}' para ver más.</i>"
    await update.message.reply_text(text, parse_mode="HTML")
    return True


# Auto-registro al importar
from schoolai.bot.text_interceptors import text_interceptors  # noqa: E402

text_interceptors.register(priority=8, name="ausencias_natural")(ausencias_interceptor)
