"""Unified LLM client factory.

Usage:
    from schoolai.skills.llm.client import get_client, parse_model, call_with_fallback

    provider, model = parse_model(settings.llm_chat)  # "groq/compound-beta"
    client = get_client(provider)

    # With automatic fallback (non-blocking):
    response = await call_with_fallback(
        primary=settings.llm_router,
        fallbacks=settings.llm_router_fallback,
        messages=[...],
        **kwargs,
    )
"""
from __future__ import annotations

import asyncio

import openai
from loguru import logger
from openai import OpenAI

from schoolai.skills.llm.providers import PROVIDERS

# One OpenAI client instance per provider (singleton per process)
_clients: dict[str, OpenAI] = {}


def parse_model(model_str: str) -> tuple[str, str]:
    """Split 'provider/model' into (provider, model).

    'zhipu/glm-4-flash'              → ('zhipu', 'glm-4-flash')
    'openrouter/mistralai/mistral-7b' → ('openrouter', 'mistralai/mistral-7b')
    'llama-3.1-8b-instant'           → ('groq', 'llama-3.1-8b-instant')  # default provider
    """
    if "/" in model_str:
        provider, model = model_str.split("/", 1)
        if provider in PROVIDERS:
            return provider, model
    return "groq", model_str


def get_client(provider: str, timeout: float = 60.0) -> OpenAI:
    """Return a cached OpenAI-compatible client for the given provider."""
    if provider not in _clients:
        from schoolai.config import settings

        info = PROVIDERS.get(provider)
        if info is None:
            raise ValueError(f"Unknown LLM provider: {provider!r}. Available: {list(PROVIDERS)}")

        api_key = getattr(settings, info["key"], "") or ""
        if not api_key:
            raise ValueError(f"API key not configured for provider {provider!r} ({info['key']})")

        kwargs: dict = {"api_key": api_key, "timeout": timeout}
        if info["base_url"]:
            kwargs["base_url"] = info["base_url"]

        _clients[provider] = OpenAI(**kwargs)

    return _clients[provider]


def _call_sync(model_str: str, messages: list[dict], **kwargs):
    """Blocking call to a single model. Runs in a thread via call_with_fallback."""
    provider, model = parse_model(model_str)
    client = get_client(provider)
    return client.chat.completions.create(model=model, messages=messages, **kwargs)


async def call_with_fallback(
    primary: str,
    fallbacks: str,
    messages: list[dict],
    **kwargs,
):
    """Try primary model, then each comma-separated fallback on 5xx / 429.

    Runs each blocking SDK call in a thread pool so the event loop stays free.
    Returns the first successful ChatCompletion response.
    Raises the last error if all models fail.
    """
    models = [primary] + [m.strip() for m in fallbacks.split(",") if m.strip()]
    last_exc: Exception | None = None

    for model_str in models:
        try:
            return await asyncio.to_thread(_call_sync, model_str, messages, **kwargs)
        except (openai.InternalServerError, openai.RateLimitError) as exc:
            logger.warning(f"[llm] {model_str} unavailable ({exc.status_code}) — trying next")
            last_exc = exc
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.warning(f"[llm] {model_str} error: {exc} — trying next")
            last_exc = exc

    raise last_exc  # type: ignore[misc]
