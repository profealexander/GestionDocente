"""Comando /ayuda — muestra las skills disponibles con botones inline."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.callback_router import callback_router

SKILLS = [
    ("📋 Tareas", "help:homework"),
    ("👥 Asistencia", "help:attendance"),
    ("💰 Cuotas", "help:cuotas"),
    ("🔍 Consultas", "help:query"),
    ("🤖 Agente IA", "help:agent"),
    ("📁 Contexto", "help:context"),
    ("⏰ Recordatorios", "help:reminders"),
    ("👤 Personas y datos", "help:db"),
    ("⚙️ Comandos", "help:commands"),
]

DESCRIPTIONS = {
    "help:homework": (
        "*Tareas*\n\n"
        "Escribe libremente describiendo la tarea:\n\n"
        "_Tarea de Matemáticas para 2do BT: resolver página 45 para el viernes._\n\n"
        "• Puedes crear tareas para varias materias a la vez\n"
        "• Editar o eliminar: _editar tarea 3 de 3ro BT_\n"
        "• Ver incumplimiento: _reporte de tareas de esta semana_"
    ),
    "help:attendance": (
        "*Asistencia*\n\n"
        "Escribe o dicta por voz quién faltó:\n\n"
        "_Hoy faltaron Juan Pérez y María López del 3ro BT._\n\n"
        "• Atrasos: _llegó tarde Carlos Torres_\n"
        "• Justificados: _justificado Pedro Gómez_\n"
        "• Editar registro: _editar asistencia de ayer de 3ro BT_\n"
        "• Puedes enviar el mensaje por voz"
    ),
    "help:cuotas": (
        "*Cuotas y actividades*\n\n"
        "Gestiona cobros de actividades escolares:\n\n"
        "_Crear actividad excursión al museo, costo 5 dólares, para 3ro BT._\n"
        "_Registrar pago de Juan Pérez en excursión._\n"
        "_¿Quién debe la cuota de la excursión?_\n\n"
        "• Exportar lista de pagos a Excel\n"
        "• Editar montos y participantes"
    ),
    "help:query": (
        "*Consultas*\n\n"
        "Pide información sobre tareas o asistencia:\n\n"
        "_Dame la asistencia de hoy del 2do BT._\n"
        "_Muestra las tareas de esta semana de Tercero BT._\n"
        "_¿Quién faltó ayer en Décimo EGB?_\n\n"
        "Períodos: hoy, esta semana, este mes, semana pasada, por trimestre"
    ),
    "help:agent": (
        "*Agente IA*\n\n"
        "El agente responde preguntas complejas combinando varias acciones:\n\n"
        "_¿Cuántos estudiantes faltaron más de 3 veces este mes?_\n"
        "_Muestra el promedio de asistencia por curso._\n"
        "_¿Cuáles son las tareas pendientes de esta semana?_\n\n"
        "• Análisis con código Python (REPL)\n"
        "• Combina datos de asistencia, tareas y cuotas\n"
        "• Usa el Bot Agente para aprovechar al máximo esta función"
    ),
    "help:context": (
        "*Contexto institucional*\n\n"
        "Guarda y consulta documentos de tu institución:\n\n"
        "_/contexto ¿cuáles son los feriados de este trimestre?_\n"
        "_/contexto https://sitio.edu.ec/reglamento_\n"
        "_/contexto El horario de clases es de 7:00 a 13:00_\n\n"
        "• Busca primero en documentos guardados\n"
        "• Si no encuentra, busca en la web automáticamente\n"
        "• Puedes guardar páginas web como referencia"
    ),
    "help:reminders": (
        "*Recordatorios*\n\n"
        "Programa avisos para fechas importantes:\n\n"
        "_Recuérdame mañana a las 8am entregar las notas._\n"
        "_Avísame el viernes que hay reunión de padres._\n\n"
        "• El bot te envía un mensaje en el horario indicado\n"
        "• Disponible en el Bot Agente"
    ),
    "help:db": (
        "*Personas y datos*\n\n"
        "Usa el comando /db para registrar:\n"
        "• Estudiantes\n"
        "• Docentes\n"
        "• Directivos y administrativos\n"
        "• Representantes\n\n"
        "El bot te guía paso a paso."
    ),
    "help:commands": (
        "*Comandos disponibles*\n\n"
        "/start — saludo inicial\n"
        "/ayuda — esta pantalla\n"
        "/cancelar — cancela el flujo actual\n"
        "/db — panel de registro de personas\n"
        "/contexto — guardar o consultar documentos\n"
        "/jornada — iniciar modo jornada manual\n"
        "/horario — ver horario de clases\n"
        "/cron — ver jobs programados\n"
        "/cron morning\\_notify 07:30 — cambiar hora de aviso matutino"
    ),
}


def _skills_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for i, (label, cb) in enumerate(SKILLS):
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 2 or i == len(SKILLS) - 1:
            buttons.append(row)
            row = []
    return InlineKeyboardMarkup(buttons)


async def handle_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "¿En qué puedo ayudarte?",
        reply_markup=_skills_keyboard(),
    )


@callback_router.register("help:back")
async def handle_help_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "¿En qué puedo ayudarte?",
        reply_markup=_skills_keyboard(),
    )


@callback_router.register("help:")
async def handle_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    text = DESCRIPTIONS.get(query.data)
    if not text:
        return
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("« Volver", callback_data="help:back")]],
        ),
    )
