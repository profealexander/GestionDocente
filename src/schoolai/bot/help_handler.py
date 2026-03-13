"""Comando /ayuda — muestra las skills disponibles con botones inline."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

SKILLS = [
    ("📋 Registrar tarea",   "help:homework"),
    ("👥 Pasar asistencia",  "help:attendance"),
    ("🔍 Consultar datos",   "help:query"),
    ("👤 Registrar personas", "help:db"),
]

DESCRIPTIONS = {
    "help:homework": (
        "*Registrar tarea*\n\n"
        "Escribe libremente describiendo la tarea:\n\n"
        "_Tarea de Matemáticas para 2do BT: resolver página 45 para el viernes._\n\n"
        "Necesito saber:\n"
        "• Qué hay que hacer\n"
        "• El curso (ej: 3ro BT, Décimo EGB)\n"
        "• La asignatura\n"
        "• La fecha de entrega (opcional)"
    ),
    "help:attendance": (
        "*Pasar asistencia*\n\n"
        "Escribe libremente mencionando quién faltó:\n\n"
        "_Hoy faltaron Juan Pérez y María López del 3ro BT._\n\n"
        "También puedes registrar:\n"
        "• Atrasos: _llegó tarde Carlos Torres_\n"
        "• Justificados: _justificado Pedro Gómez_\n\n"
        "Puedes enviar el mensaje por voz."
    ),
    "help:query": (
        "*Consultar datos*\n\n"
        "Pide información sobre tareas o asistencia:\n\n"
        "_Dame la asistencia de hoy del 2do BT._\n"
        "_Muestra las tareas de esta semana de Tercero BT._\n"
        "_¿Quién faltó ayer en Décimo EGB?_\n\n"
        "Períodos disponibles:\n"
        "• Hoy, esta semana, este mes\n"
        "• Semana pasada, mes pasado\n"
        "• Por trimestre"
    ),
    "help:db": (
        "*Registrar personas*\n\n"
        "Usa el comando /db para registrar:\n"
        "• Estudiantes\n"
        "• Docentes\n"
        "• Directivos\n"
        "• Administrativos\n"
        "• Representantes\n\n"
        "El bot te guiará paso a paso para elegir el rol, "
        "ingresar la lista de nombres y confirmar."
    ),
}


def _skills_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(label, callback_data=cb)] for label, cb in SKILLS]
    return InlineKeyboardMarkup(buttons)


async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "¿En qué puedo ayudarte?",
        reply_markup=_skills_keyboard(),
    )


async def handle_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text = DESCRIPTIONS.get(query.data)
    if not text:
        return
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("« Volver", callback_data="help:back")]
        ]),
    )


async def handle_help_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "¿En qué puedo ayudarte?",
        reply_markup=_skills_keyboard(),
    )
