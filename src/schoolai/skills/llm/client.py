"""Unified LLM client factory.

Usage:
    from schoolai.skills.llm.client import get_client, parse_model

    provider, model = parse_model(settings.llm_chat)  # "groq/llama-3.3-70b-versatile"
    client = get_client(provider)
    response = client.chat.completions.create(model=model, ...)
"""

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
