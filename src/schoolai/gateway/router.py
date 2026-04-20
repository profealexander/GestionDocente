"""
LLM-based domain/intent classifier using Structured Output.
Returns domain, intent, and extracted entities.
"""
from __future__ import annotations

import json

from schoolai.config import settings
from schoolai.skills.llm.client import get_client, parse_model

_SYSTEM = """
You are a classifier for a school management assistant.

Given a teacher's message, return JSON with:
- domain: one of [attendance, homework, cuotas, web_search, general]
- intent: one of [query, record, delete, search, chat]
- entities: list of names, dates, course codes, or other key tokens extracted from the message

Respond ONLY with valid JSON. No explanation.

Examples:
  "Falta Tatiana y Mario 3BT" → {"domain":"attendance","intent":"record","entities":["Tatiana","Mario","3BT"]}
  "Faltas de hoy" → {"domain":"attendance","intent":"query","entities":[]}
  "Tarea de matemáticas para el viernes" → {"domain":"homework","intent":"record","entities":["matemáticas","viernes"]}
  "¿Cuánto debe Pedro?" → {"domain":"cuotas","intent":"query","entities":["Pedro"]}
  "Busca información sobre fracciones" → {"domain":"web_search","intent":"search","entities":["fracciones"]}
"""


async def classify(text: str) -> dict:
    provider, model = parse_model(settings.llm_router)
    client = get_client(provider)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": text},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"domain": "general", "intent": "chat", "entities": []}
