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
    QueryExtract,
)

_client: ZhipuAI | None = None

SYSTEM_PROMPT = """Eres un extractor de datos para un sistema de gestión escolar.
Analiza el mensaje del docente y responde ÚNICAMENTE con un JSON válido, sin explicaciones.

Intenciones posibles:
- attendance: registrar faltas, atrasos o justificaciones
- homework: registrar tarea, actividad, proyecto o evaluación
- query: consultar datos existentes (pide ver, muestra, dame, lista)
- chat: cualquier otra cosa

Para attendance:
{
  "intent": "attendance",
  "names": ["nombre completo"],
  "course": "curso mencionado o null",
  "date": "today|yesterday|YYYY-MM-DD",
  "status": "absent|late|justified",
  "complete": true/false
}
complete=false si course es null.
status por defecto: "absent". Si dice "tardó/atraso": "late". Si dice "justificado": "justified".
date por defecto: "today".

Para homework:
{
  "intent": "homework",
  "description": "descripción de la tarea",
  "course": "curso o null",
  "subject": "materia o null",
  "delivery_date": "YYYY-MM-DD|nombre del día|null",
  "complete": true/false
}
complete=false si course es null o subject es null.

Para query:
{
  "intent": "query",
  "query_type": "attendance|homework",
  "course": "curso o null",
  "period": "today|yesterday|week|last_week|month|last_month|trimester",
  "complete": true/false
}
complete=false si course es null.
period por defecto: "today" para attendance, "trimester" para homework.

Para chat:
{
  "intent": "chat"
}"""


def _get_client() -> ZhipuAI:
    global _client
    if _client is None:
        _client = ZhipuAI(api_key=settings.glm_api_key)
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
        data = QueryExtract(
            query_type=raw.get("query_type", "attendance"),
            course=raw.get("course"),
            period=raw.get("period", "today"),
            complete=bool(raw.get("complete", False)),
        )
    else:
        data = ChatExtract()

    return ExtractionResult(intent=intent, data=data)


async def extract(text: str, history: list[dict] | None = None) -> ExtractionResult:
    """Extrae intent y entidades del mensaje. history = últimos intercambios [{role, content}]."""
    if not settings.glm_api_key:
        return ExtractionResult(intent="chat", data=ChatExtract())

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-6:])  # últimos 3 intercambios
    messages.append({"role": "user", "content": text})

    try:
        def _call():
            return _get_client().chat.completions.create(
                model="glm-4.5-air",
                messages=messages,
                extra_body={"temperature": 0.1},
                stream=False,
            )

        response = await asyncio.to_thread(_call)
        content = response.choices[0].message.content.strip()

        # Extraer JSON aunque el modelo agregue texto extra
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON found in: {content}")

        raw = json.loads(match.group())
        result = _build_result(raw)
        logger.info(f"[extractor] intent={result.intent} complete={getattr(result.data, 'complete', True)}")
        return result

    except Exception as e:
        logger.error(f"[extractor] error: {e}")
        return ExtractionResult(intent="chat", data=ChatExtract())
