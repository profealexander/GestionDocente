from loguru import logger
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from schoolai.bot.action_handler import resolve_selection_text
from schoolai.bot.mode import is_jornada
from schoolai.bot.transcription import transcribe
from schoolai.bot.whatsapp_handler import handle_wa_setup_text
from schoolai.config import settings
from schoolai.skills.registry import registry
from schoolai.skills.utils.courses import (
    _ABBREV_TO_NAME,
    _NAME_TO_ABBREV,
    COURSE_GROUP_ALIASES,
    course_abbrev_map,
)

# Textos que activan el Modo Jornada — solo se evalúan cuando is_jornada() es True
_JORNADA_TRIGGERS = {"j", "J", "1", "jornada", "Jornada", "iniciar", "Iniciar", "📅 Jornada"}

JORNADA_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("📅 Jornada")]],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Escribe o toca 📅 Jornada...",
)
REMOVE_KEYBOARD = ReplyKeyboardRemove()


def is_allowed(user_id: int) -> bool:
    allowed = settings.allowed_user_ids
    return not allowed or user_id in allowed


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        logger.warning(f"Unauthorized user {user.id}")
        return

    text = update.message.text.strip()
    logger.info(f"[text] user={user.id} (@{user.username}): {text[:200]}")
    logger.debug(f"[text:full] user={user.id}: {text}")

    await _dispatch(update, user.id, text, context)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        logger.warning(f"Unauthorized user {user.id}")
        return

    if not settings.groq_api_key:
        await update.message.reply_text("Transcripción de audio no configurada.")
        return

    await update.message.reply_text("Transcribiendo audio...")

    voice = update.message.voice or update.message.audio
    tg_file = await context.bot.get_file(voice.file_id)
    audio_bytes = await tg_file.download_as_bytearray()

    try:
        text = await transcribe(bytes(audio_bytes), "audio.ogg", settings.groq_api_key)
        logger.info(f"[voice] {user.id}: {text[:80]}")
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        await update.message.reply_text(
            "Error al transcribir el audio. Intenta enviarlo como texto.",
        )
        return

    await update.message.reply_text(f'Escuché: "{text}"')
    await _dispatch(update, user.id, text, context)


def _detect_course_only(text: str) -> tuple[str, int, str] | None:
    """Returns (abbrev, grade_id, grade_name) when the message is just a course reference."""
    t = text.strip()

    # Path 1: verbal name  ("primero bt", "octavo egb")
    canonical = t.upper()
    abbrev = _NAME_TO_ABBREV.get(canonical)
    if abbrev and abbrev in course_abbrev_map:
        return abbrev, course_abbrev_map[abbrev], canonical

    # Path 2: abbreviation ("1bt", "8egb", "prep")
    abbrev = t.lower().replace(" ", "")
    if abbrev in course_abbrev_map:
        grade_name = _ABBREV_TO_NAME.get(abbrev, abbrev.upper())
        return abbrev, course_abbrev_map[abbrev], grade_name

    return None


async def _show_course_action_menu(update: Update, course_info: tuple) -> None:
    abbrev, _grade_id, grade_name = course_info
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📝 Registrar tarea", callback_data=f"course_action:hw:{abbrev}",
                ),
                InlineKeyboardButton(
                    "✅ Registrar asistencia", callback_data=f"course_action:att:{abbrev}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📋 Ver tareas", callback_data=f"course_action:query_hw:{abbrev}",
                ),
                InlineKeyboardButton(
                    "📊 Cumplimiento", callback_data=f"course_action:compliance:{abbrev}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📈 Ver asistencia hoy", callback_data=f"course_action:query_att:{abbrev}",
                ),
            ],
        ],
    )
    await update.message.reply_text(
        f"¿Qué deseas hacer con <b>{grade_name.title()}</b>?",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


def _detect_course_group(text: str) -> list[tuple[str, str]] | None:
    """Detecta si el texto es un alias de grupo (ej. 'bachillerato').

    Retorna lista de (abbrev, grade_name) de los cursos del grupo,
    o None si no es un alias conocido o los cursos no están en el mapa.
    """
    key = text.strip().lower()
    abbrevs = COURSE_GROUP_ALIASES.get(key)
    if not abbrevs:
        return None
    courses = [
        (a, _ABBREV_TO_NAME.get(a, a.upper()))
        for a in abbrevs
        if a in course_abbrev_map
    ]
    return courses or None


async def _show_course_group_menu(update: Update, courses: list[tuple[str, str]]) -> None:
    """Muestra un teclado para elegir el curso específico dentro del grupo."""
    buttons = [
        [InlineKeyboardButton(name.title(), callback_data=f"course_action:pick:{abbrev}")]
        for abbrev, name in courses
    ]
    await update.message.reply_text(
        "¿A cuál curso te refieres?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _dispatch(update: Update, user_id: int, text: str, context: ContextTypes.DEFAULT_TYPE = None) -> None:
    """Despacha el mensaje al skill correcto a través de capas de intercepción.

    Capas (en orden):
      0. Jornada triggers — solo en modo jornada
      1. Selección pendiente (botones inline)
      2. Setup de WhatsApp activo
      3. Input numérico para cuotas (PendingCuotaCreate)
      4. SkillRegistry.detect_all() → Planner si multi-intent
    """
    # Capa 0: atajos de jornada — solo en modo jornada
    if is_jornada():
        if text in _JORNADA_TRIGGERS:
            from schoolai.bot.jornada_handler import handle_jornada_command

            await handle_jornada_command(update, context)
            return
        # Si no hay sesión o está terminada, las skills funcionan igual que el bot libre.
        # Solo bloqueamos cuando el texto es ambiguo y no hay sesión iniciada
        # (el pipeline de skills sigue corriendo debajo).

    if await resolve_selection_text(update, user_id):
        return

    if await handle_wa_setup_text(update):
        return

    from schoolai.bot.broadcast_handler import handle_broadcast_text
    if await handle_broadcast_text(update, context):
        return

    from schoolai.bot.text_interceptors import text_interceptors

    if await text_interceptors.run(update, user_id):
        return

    # Detección + ejecución
    skills = registry.detect_all(text)

    if not skills:
        # Ninguna skill específica → ChatSkill fallback
        skill = registry.detect(text)
        logger.info(f"[dispatch] intent={skill.intent} user={user_id}")
        await skill.handle(update, user_id, text)
        return

    if len(skills) == 1:
        logger.info(f"[dispatch] intent={skills[0].intent} user={user_id}")
        await skills[0].handle(update, user_id, text)
        return

    # Múltiples skills — Planner divide el texto y asigna fragmentos
    logger.info(f"[dispatch] multi-intent={[s.intent for s in skills]} user={user_id}")
    from schoolai.skills.planner import plan

    for skill, fragment in plan(text, skills):
        await skill.handle(update, user_id, fragment)
