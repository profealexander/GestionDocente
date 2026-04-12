"""Widgets de UI compartidos y constantes de estado."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from schoolai.skills.attendance.constants import ABSENT, JUSTIFIED, LATE

STATUS_MAP = {
    "absent": ABSENT,
    "late": LATE,
    "justified": JUSTIFIED,
}

_HW_STATUS_LABELS: dict[str, str] = {
    "missing": "No entregaron",
    "late": "Entregaron tarde",
    "partial": "Entrega parcial",
}


def _sel_keyboard(options: list[dict]) -> InlineKeyboardMarkup:
    """Builds inline keyboard for any selection. ≤3 in one row, else one per row."""
    buttons = [
        InlineKeyboardButton(
            f"{i}. {opt['label']}",
            callback_data=f"sel:{opt['value']}",
        )
        for i, opt in enumerate(options, 1)
    ]
    rows = [buttons] if len(buttons) <= 3 else [[b] for b in buttons]
    return InlineKeyboardMarkup(rows)
