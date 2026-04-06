"""Fire-and-forget LLM usage recorder.

Captura tokens de entrada/salida/cache de cada respuesta LLM y los persiste
en la tabla llm_usage sin bloquear el flujo principal.

Usage:
    from schoolai.skills.llm.usage import fire_record_usage
    fire_record_usage(provider="google", model="gemini-2.5-flash-lite", response=resp, agent="attendance")
"""

from __future__ import annotations

import asyncio

from loguru import logger


def fire_record_usage(
    provider: str,
    model: str,
    response: object,
    agent: str = "unknown",
) -> None:
    """Lee response.usage y lanza INSERT en background (zero latencia)."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return

    prompt = getattr(usage, "prompt_tokens", 0) or 0
    completion = getattr(usage, "completion_tokens", 0) or 0

    # Gemini / OpenAI prompt caching
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details:
        cached = getattr(details, "cached_tokens", 0) or 0

    try:
        asyncio.get_running_loop().create_task(
            _write_usage(provider, model, agent, prompt, completion, cached)
        )
    except RuntimeError:
        # Sin event loop activo (tests síncronos) — ignorar silenciosamente
        pass


async def _write_usage(
    provider: str,
    model: str,
    agent: str,
    prompt: int,
    completion: int,
    cached: int,
) -> None:
    from schoolai.db.connection import async_session
    from schoolai.db.models.llm_usage import LLMUsage

    try:
        async with async_session() as session:
            session.add(
                LLMUsage(
                    provider=provider,
                    model=model,
                    agent=agent,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    cached_tokens=cached,
                )
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[llm_usage] write failed: {e}")
