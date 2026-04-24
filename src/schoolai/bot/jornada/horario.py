"""Comando /horario y detección por lenguaje natural."""

import re
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from schoolai.bot.state import DAY_NAMES
from schoolai.db.connection import get_db_session
from schoolai.skills.db.schedule_service import get_schedule_for_day, get_teacher_by_telegram
from schoolai.bot.jornada.helpers import _ORDINAL, _extract_day_from_text

# ── Tiempos estándar por número de hora (bachillerato, 8 horas) ───────────────

_PERIOD_TIMES: dict[int, tuple[str, str]] = {
    1: ("07:30", "08:15"),
    2: ("08:15", "09:00"),
    3: ("09:00", "09:45"),
    4: ("09:45", "10:30"),
    5: ("10:50", "11:30"),
    6: ("11:30", "12:10"),
    7: ("12:10", "12:50"),
    8: ("12:50", "13:30"),
}
_TOTAL_PERIODS = 8
_BREAK_BEFORE = 5  # receso antes de la hora 5

_ORDINAL_TO_NUM = {
    "PRIMERO": "1", "PRIMERA": "1", "SEGUNDO": "2", "SEGUNDA": "2",
    "TERCERO": "3", "TERCERA": "3", "CUARTO": "4", "CUARTA": "4",
    "QUINTO": "5", "SEXTO": "6", "SEPTIMO": "7", "SÉPTIMO": "7",
    "OCTAVO": "8", "NOVENO": "9", "DECIMO": "10", "DÉCIMO": "10",
    "INICIAL": "I", "PREPARATORIA": "P",
}
_STOP_WORDS = {"y", "de", "del", "la", "el", "los", "las", "con", "en", "a", "e", "o"}

_HORARIO_RE = re.compile(
    r"\b(horario|mi horario|ver horario|clases?(?: de)?(?: hoy| ma[nñ]ana)?|"
    r"qu[eé] tengo(?: hoy| ma[nñ]ana)?|"
    r"qu[eé] clases?(?: tengo)?)\b",
    re.IGNORECASE,
)


def _grade_abbrev(name: str) -> str:
    """'PRIMERO BT' → '1BT', 'OCTAVO EGB' → '8EGB'"""
    parts = name.upper().split()
    num = _ORDINAL_TO_NUM.get(parts[0], parts[0])
    level = parts[-1] if len(parts) > 1 else ""
    return f"{num}{level}" if level in ("BT", "EGB") else num


def _subject_abbrev(name: str) -> str:
    """'Contabilidad General' → 'CG'"""
    words = [w for w in name.split() if w.lower() not in _STOP_WORDS and len(w) > 2]
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(w[0].upper() for w in words)


def _build_schedule_text(periods: list, day: int) -> str:
    by_num = {p.period_num: p for p in periods}
    day_name = DAY_NAMES[day].upper()
    lines = [f"📅 *{day_name}*", ""]
    for h in range(1, _TOTAL_PERIODS + 1):
        if h == _BREAK_BEFORE:
            lines.append("")
        start = _PERIOD_TIMES.get(h, ("—:—", "—:—"))[0]
        ord_label = _ORDINAL.get(h, str(h))
        if h in by_num:
            p = by_num[h]
            grade = _grade_abbrev(p.grade.name)
            subj = _subject_abbrev(p.subject.name)
            lines.append(f"`{ord_label}` {start}  {grade} · {subj}")
        else:
            lines.append(f"`{ord_label}` {start}  —")
    return "\n".join(lines)


def _day_nav_keyboard(current_day: int) -> InlineKeyboardMarkup:
    labels = ["LUN", "MAR", "MIÉ", "JUE", "VIE"]
    buttons = [
        InlineKeyboardButton(
            f"·{labels[d]}·" if d == current_day else labels[d],
            callback_data=f"hor_day:{d}",
        )
        for d in range(5)
    ]
    return InlineKeyboardMarkup([buttons])


async def handle_horario_command(update, context) -> None:
    user_id = update.effective_user.id
    today = date.today().weekday()
    if today > 4:
        today = 0  # fin de semana → mostrar lunes

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await update.message.reply_text(
                "No tienes un perfil de docente vinculado.\n"
                "Usa /db → 📅 Horario para configurarlo.",
            )
            return
        periods = await get_schedule_for_day(session, teacher.id, today)

    await update.message.reply_text(
        _build_schedule_text(periods, today),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_day_nav_keyboard(today),
    )


async def handle_horario_callback(update, context) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    day = int(query.data.split(":")[1])

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            await query.edit_message_text("Perfil de docente no encontrado.")
            return
        periods = await get_schedule_for_day(session, teacher.id, day)

    await query.edit_message_text(
        _build_schedule_text(periods, day),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_day_nav_keyboard(day),
    )


async def _horario_interceptor(update, user_id: int) -> bool:
    """Detecta solicitudes de horario en lenguaje natural."""
    text = update.message.text
    if not _HORARIO_RE.search(text):
        return False

    day = _extract_day_from_text(text)
    if day > 4:
        day = 0

    async with get_db_session() as session:
        teacher = await get_teacher_by_telegram(session, user_id)
        if not teacher:
            return False
        periods = await get_schedule_for_day(session, teacher.id, day)

    await update.message.reply_text(
        _build_schedule_text(periods, day),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_day_nav_keyboard(day),
    )
    return True


# Auto-registro al importar
from schoolai.bot.text_interceptors import text_interceptors  # noqa: E402

text_interceptors.register(priority=8, name="horario_natural")(_horario_interceptor)
