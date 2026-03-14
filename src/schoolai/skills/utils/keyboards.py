"""Keyboards de Telegram reutilizables."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def grade_keyboard(grades: list, callback_prefix: str) -> InlineKeyboardMarkup:
    """Teclado inline de cursos con prefijo de callback configurable.

    callback_prefix: p.ej. 'att_grade', 'qry_grade', 'db_grade'
    El callback_data generado es: '{prefix}:{grade.id}' o '{prefix}:{grade.id}:{grade.name}'
    según si el prefijo termina en _name o no.

    Para att_grade y db_grade el formato es '{prefix}:{id}:{name}'.
    Para qry_grade el formato es '{prefix}:{id}'.
    """
    include_name = callback_prefix in ("att_grade", "db_grade", "act_grade")
    buttons = []
    row = []
    for g in grades:
        if include_name:
            cb = f"{callback_prefix}:{g.id}:{g.name}"
        else:
            cb = f"{callback_prefix}:{g.id}"
        row.append(InlineKeyboardButton(g.name, callback_data=cb))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)
