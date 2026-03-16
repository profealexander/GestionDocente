"""Extractor de intención y entidades usando GLM."""

import asyncio
import json
import re
from datetime import date, timedelta

from loguru import logger
from zhipuai import ZhipuAI

from schoolai.config import settings
from schoolai.skills.extractor.schema import (
    AttendanceExtract,
    ChatExtract,
    ExtractionResult,
    HomeworkExtract,
    HomeworkReportExtract,
    QueryExtract,
)

_client: ZhipuAI | None = None
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# Mapa estático: abreviatura → nombre canónico en BD
# (cargado con IDs reales en _course_map al iniciar)
_NAME_TO_ABBREV: dict[str, str] = {
    "INICIAL 1": "i1",    "INICIAL 2": "i2",
    "PREPARATORIA": "prep",
    "SEGUNDO EGB": "2egb", "TERCERO EGB": "3egb",  "CUARTO EGB": "4egb",
    "QUINTO EGB":  "5egb", "SEXTO EGB":   "6egb",  "SEPTIMO EGB": "7egb",
    "OCTAVO EGB":  "8egb", "NOVENO EGB":  "9egb",  "DECIMO EGB":  "10egb",
    "PRIMERO BT":  "1bt",  "SEGUNDO BT":  "2bt",   "TERCERO BT":  "3bt",
}

# abbrev → grade_id, poblado en load_course_map()
course_abbrev_map: dict[str, int] = {}


async def load_course_map() -> None:
    """Carga abrev→grade_id desde la BD. Llamar al arrancar el bot."""
    from sqlalchemy import select
    from schoolai.db.connection import async_session
    from schoolai.db.models.grade import Grade

    async with async_session() as session:
        grades = (await session.execute(select(Grade))).scalars().all()
    for g in grades:
        abbrev = _NAME_TO_ABBREV.get(g.name)
        if abbrev:
            course_abbrev_map[abbrev] = g.id
    logger.info(f"[extractor] course_map cargado: {len(course_abbrev_map)} cursos")


def _course_list_str() -> str:
    return ",".join(_NAME_TO_ABBREV.values())


_SYSTEM_PROMPT_TEMPLATE = """You are a data extractor for a school management system.
Analyze the teacher's message (written in Spanish) and reply ONLY with valid JSON, no explanations.

Intents:
- attendance: recording absences, tardiness, or justified absences
- homework: registering an assignment, project, or evaluation
- query: requesting existing data (keywords: ver, dame, muestra, lista, tareas de, asistencia de)
- homework_report: reporting who did not complete an assignment
- chat: anything else

attendance:
{{"intent":"attendance","names":["full name"],"course":"course or null","date":"today|yesterday|YYYY-MM-DD","status":"absent|late|justified","complete":true/false}}
- complete=false if course is null
- status default: "absent" | "tardó/atraso" → "late" | "justificado" → "justified"
- date default: "today"

homework:
{{"intent":"homework","description":"corrected full description","course":"course or null","subject":"subject or null","delivery_date":"YYYY-MM-DD|weekday name|null","complete":true/false}}
- complete=false if course or subject is null
- description: fix spelling, expand abbreviations (pag.→página, ej.→ejercicio), write clearly

query:
{{"intent":"query","query_type":"attendance|homework","courses":["abbrev1","abbrev2"],"period":"today|yesterday|week|last_week|month|last_month|trimester","complete":true/false}}
- complete=false if courses is empty
- period default: "today" for attendance, "trimester" for homework
- courses: list of abbreviations from the table below, [] if none mentioned
- Available courses: {course_list}
- Groups: bachillerato→[1bt,2bt,3bt] | básica superior→[8egb,9egb,10egb] | básica media→[5egb,6egb,7egb] | básica elemental→[2egb,3egb,4egb] | egb→[prep,2egb,3egb,4egb,5egb,6egb,7egb,8egb,9egb,10egb] | inicial→[i1,i2]
- Handle typos: "optabo"→8egb, "nobeno"→9egb, "pimero bc"→1bt, "desimo"→10egb

homework_report:
{{"intent":"homework_report","names":["full name"],"homework_ref":number or null,"course":"course or null","subject":"subject or null","status":"missing|late|partial","complete":true/false}}
- complete=false if course is null
- status default: "missing" | "tarde/atrasado" → "late" | "incompleto/parcial" → "partial"
- homework_ref: integer if message says "tarea 3", "la 2", "#1", else null

chat:
{{"intent":"chat"}}

Edge cases → always return valid JSON:
- "X no entregó esta tarea" (no ref, no subject, no course) → homework_report with complete=false
- "dame reporte de tareas de [student]" → chat (student-level queries not supported)
- "quién no entregó" without course → homework_report with complete=false
- Any unclear message → chat, never return empty"""


def _get_system_prompt() -> str:
    return _SYSTEM_PROMPT_TEMPLATE.format(course_list=_course_list_str())


def _get_client() -> ZhipuAI:
    global _client
    if _client is None:
        _client = ZhipuAI(
            api_key=settings.glm_api_key,
            timeout=30.0,   # extractor JSON: respuesta corta, 30s es más que suficiente
        )
    return _client


def _parse_date(value: str) -> date:
    today = date.today()
    if value == "today":
        return today
    if value == "yesterday":
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(value)
    except ValueError:
        return today


def _resolve_delivery(value: str | None) -> date | None:
    if not value:
        return None
    today = date.today()
    day_map = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5,
    }
    v = value.lower().strip()
    if v in day_map:
        target = day_map[v]
        days_ahead = (target - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead)
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _build_result(raw: dict) -> ExtractionResult:
    intent = raw.get("intent", "chat")

    if intent == "attendance":
        data = AttendanceExtract(
            names=raw.get("names", []),
            course=raw.get("course"),
            date=raw.get("date", "today"),
            status=raw.get("status", "absent"),
            complete=bool(raw.get("complete", False)),
        )
    elif intent == "homework":
        data = HomeworkExtract(
            description=raw.get("description", ""),
            course=raw.get("course"),
            subject=raw.get("subject"),
            delivery_date=raw.get("delivery_date"),
            complete=bool(raw.get("complete", False)),
        )
    elif intent == "query":
        courses = raw.get("courses", [])
        if isinstance(courses, str):   # por si el LLM devuelve string en vez de lista
            courses = [courses] if courses else []
        data = QueryExtract(
            query_type=raw.get("query_type", "attendance"),
            courses=courses,
            period=raw.get("period", "today"),
            complete=bool(raw.get("complete", False)),
        )
    elif intent == "homework_report":
        data = HomeworkReportExtract(
            names=raw.get("names", []),
            homework_ref=raw.get("homework_ref"),
            course=raw.get("course"),
            subject=raw.get("subject"),
            status=raw.get("status", "missing"),
            complete=bool(raw.get("complete", False)),
        )
    else:
        data = ChatExtract()

    return ExtractionResult(intent=intent, data=data)


async def extract(text: str, history: list[dict] | None = None) -> ExtractionResult | None:
    """Extrae intent y entidades del mensaje. Retorna None si la extracción falla.

    history = últimos intercambios [{role, content}]
    """
    if not settings.glm_api_key:
        return ExtractionResult(intent="chat", data=ChatExtract())

    messages = [{"role": "system", "content": _get_system_prompt()}]
    if history:
        messages.extend(history[-6:])  # últimos 3 intercambios
    messages.append({"role": "user", "content": text})

    def _call(temperature: float, top_p: float):
        return _get_client().chat.completions.create(
            model="glm-4.5-air",
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=500,
            stream=False,
        )

    try:
        response = await asyncio.to_thread(_call, 0.1, 0.2)
        content = response.choices[0].message.content.strip()

        match = _JSON_RE.search(content)
        if not match:
            # Primer intento vacío — retry con parámetros más permisivos
            logger.warning(f"[extractor] no JSON (attempt 1) — raw: {content!r}, retrying...")
            response = await asyncio.to_thread(_call, 0.3, 0.7)
            content = response.choices[0].message.content.strip()
            match = _JSON_RE.search(content)

        if not match:
            logger.error(f"[extractor] no JSON after retry — raw: {content!r}")
            return None

        raw = json.loads(match.group())
        result = _build_result(raw)
        logger.debug(f"[extractor] raw={match.group()}")
        logger.info(f"[extractor] intent={result.intent} complete={getattr(result.data, 'complete', True)}")
        return result

    except Exception as e:
        logger.error(f"[extractor] error: {e}")
        return None
