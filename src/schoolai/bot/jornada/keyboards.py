"""Teclados estáticos del Modo Jornada."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_ABSENT_REASONS: dict[str, str] = {
    "meeting": "📋 Reunión delegada",
    "permit":  "📝 Permiso",
    "sick":    "🤒 Enfermedad / Malestar",
    "other":   "❓ Otro motivo",
}

_ABSENT_REASON_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("📋 Reunión delegada", callback_data="jor_absent_reason:meeting"),
            InlineKeyboardButton("📝 Permiso",          callback_data="jor_absent_reason:permit"),
        ],
        [
            InlineKeyboardButton("🤒 Enfermedad",       callback_data="jor_absent_reason:sick"),
            InlineKeyboardButton("❓ Otro motivo",      callback_data="jor_absent_reason:other"),
        ],
    ],
)

_ABSENT_DAY_REASON_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("📋 Reunión delegada", callback_data="jor_absent_day_reason:meeting"),
            InlineKeyboardButton("📝 Permiso",          callback_data="jor_absent_day_reason:permit"),
        ],
        [
            InlineKeyboardButton("🤒 Enfermedad",       callback_data="jor_absent_day_reason:sick"),
            InlineKeyboardButton("❓ Otro motivo",      callback_data="jor_absent_day_reason:other"),
        ],
    ],
)

_MORNING_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("🟢 Iniciar Modo Jornada", callback_data="jor_start")],
        [InlineKeyboardButton("🔴 No asistiré hoy",      callback_data="jor_absent_day")],
    ],
)

_FINISHED_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("🔄 Recorrer desde el inicio", callback_data="jor_restart"),
            InlineKeyboardButton("📋 Seleccionar período",       callback_data="jor_pick"),
        ],
        [
            InlineKeyboardButton("📅 Cambiar día",              callback_data="jor_day_pick"),
        ],
    ],
)

_DAY_LABELS = ["LUN", "MAR", "MIÉ", "JUE", "VIE"]


def day_pick_keyboard(current_dow: int) -> InlineKeyboardMarkup:
    """Muestra lunes–viernes; el día actual aparece marcado."""
    buttons = [
        InlineKeyboardButton(
            f"·{_DAY_LABELS[d]}·" if d == current_dow else _DAY_LABELS[d],
            callback_data=f"jor_day:{d}",
        )
        for d in range(5)
    ]
    return InlineKeyboardMarkup([buttons])


def _active_keyboard(has_prev: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("▶️ Siguiente clase", callback_data="jor_next"),
            InlineKeyboardButton("⏸ Pausar",           callback_data="jor_pause"),
        ],
    ]
    if has_prev:
        rows.append([InlineKeyboardButton("⬅️ Clase anterior", callback_data="jor_back")])
    return InlineKeyboardMarkup(rows)
