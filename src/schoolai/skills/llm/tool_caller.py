"""Helper compartido para tool calling con Groq.

Centraliza la lógica HTTP para que cada skill solo defina sus tools
y el mapeo tool_name → dataclass.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    pass


async def call_groq_tools(
    text: str,
    tools: list,           # list[ToolDef]
    system_prompt: str,
) -> tuple[str, dict] | None:
    """Llama a Groq con tool definitions y retorna (tool_name, args) o None.

    Args:
        text:          mensaje del usuario
        tools:         lista de ToolDef con .to_groq()
        system_prompt: instrucción del sistema para el modelo

    Returns:
        (tool_name, args_dict) si Groq llamó una tool, None en caso contrario.
    """
    from schoolai.config import settings
    from schoolai.skills.llm import get_client, parse_model

    if not settings.groq_api_key:
        return None

    provider, model = parse_model(settings.llm_extractor)

    try:
        client = get_client(provider)
    except ValueError as e:
        logger.warning(f"[tool_caller] cliente no disponible: {e}")
        return None

    groq_tools = [t.to_groq() for t in tools]
    messages   = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": text},
    ]

    def _call():
        return client.chat.completions.create(
            model=model,
            messages=messages,
            tools=groq_tools,
            tool_choice="auto",
            temperature=0,
        )

    try:
        response = await asyncio.to_thread(_call)
    except Exception as e:
        logger.warning(f"[tool_caller] error en llamada: {e}")
        return None

    choice = response.choices[0]
    if not choice.message.tool_calls:
        logger.debug("[tool_caller] Groq no llamó ninguna tool")
        return None

    tc = choice.message.tool_calls[0]
    try:
        args = json.loads(tc.function.arguments)
    except json.JSONDecodeError:
        logger.warning(f"[tool_caller] JSON inválido: {tc.function.arguments!r}")
        return None

    logger.info(f"[tool_caller] tool={tc.function.name} args={args}")
    return tc.function.name, args
