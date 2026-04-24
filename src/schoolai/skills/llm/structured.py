"""Structured output portable para cualquier provider OpenAI-compatible.

Estrategia elegida (compatible con todos los providers del stack):
  - response_format={"type": "json_object"}  → fuerza JSON sintácticamente válido
  - JSON schema del modelo Pydantic en el system prompt → guía la estructura
  - model_validate_json() → validación de tipos + fallback con regex

NO usar:
  - client.beta.chat.completions.parse() → solo OpenAI oficial
  - response_format={"type": "json_schema"} → no soportado por todos los providers
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TypeVar

from loguru import logger
from pydantic import BaseModel, ValidationError

from schoolai.skills.llm.client import get_client, parse_model
from schoolai.skills.llm.usage import fire_record_usage

T = TypeVar("T", bound=BaseModel)


def _safe_parse(raw: str, model_cls: type[T]) -> T | None:
    """Parsea JSON en `raw` y valida contra `model_cls`. Retorna None si falla."""
    # Intento 1: JSON directo
    try:
        return model_cls.model_validate_json(raw)
    except (json.JSONDecodeError, ValidationError, ValueError):
        pass

    # Intento 2: extraer bloque JSON si el LLM añadió texto o markdown fence
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return model_cls.model_validate_json(m.group())
        except (json.JSONDecodeError, ValidationError, ValueError):
            pass

    logger.warning(
        f"[structured] parse failed for {model_cls.__name__}: {raw[:200]!r}"
    )
    return None


async def llm_structured_output(
    prompt: str,
    model_cls: type[T],
    provider_model: str,
    *,
    system_prefix: str = "",
    temperature: float = 0,
    timeout: float = 30.0,
    agent: str = "structured",
) -> T | None:
    """Llama al LLM y retorna una instancia validada de `model_cls`, o None.

    Compatible con todos los providers OpenAI-compatible (Gemini, DeepSeek,
    Mistral, Groq, etc.) sin requerir features propietarios.

    Args:
        prompt: Mensaje del usuario con los datos a estructurar.
        model_cls: Clase Pydantic BaseModel que define la estructura esperada.
        provider_model: String "provider/model", e.g. "google/gemini-3.1-flash-lite-preview".
        system_prefix: Instrucciones adicionales antes del schema en el system prompt.
        temperature: Temperatura de generación (0 = determinista).
        timeout: Timeout en segundos para la llamada HTTP.
        agent: Etiqueta para el registro de uso en llm_usage.
    """
    schema_str = json.dumps(model_cls.model_json_schema(), indent=2, ensure_ascii=False)
    system = (
        f"{system_prefix}\n\nRespond ONLY with valid JSON matching this schema:\n{schema_str}"
        if system_prefix
        else f"Respond ONLY with valid JSON matching this schema:\n{schema_str}"
    )

    provider, model = parse_model(provider_model)
    client = get_client(provider, timeout=timeout)

    def _call():
        return client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
        )

    response = await asyncio.to_thread(_call)
    fire_record_usage(provider=provider, model=model, response=response, agent=agent)
    raw = (response.choices[0].message.content or "").strip()
    return _safe_parse(raw, model_cls)
