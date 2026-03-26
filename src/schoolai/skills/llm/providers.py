"""Registry of LLM providers — base_url + which settings key holds the API key."""

# provider_name → {"base_url": str | None, "key": settings attribute name}
PROVIDERS: dict[str, dict] = {
    # Z.AI — international endpoint (GLM-4.7-Flash, GLM-4.7, etc.)
    # Docs: https://docs.z.ai/api-reference/llm/chat-completion
    "zai": {
        "base_url": "https://api.z.ai/api/paas/v4/",
        "key": "zai_api_key",
    },
    # ZhipuAI — China endpoint (legacy, mantener para compatibilidad)
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "key": "zhipu_api_key",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1/",
        "key": "mistral_api_key",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/",
        "key": "deepseek_api_key",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1/",
        "key": "moonshot_api_key",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1/",
        "key": "nvidia_api_key",
    },
    "minimax": {
        "base_url": "https://api.minimaxi.chat/v1/",
        "key": "minimax_api_key",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1/",
        "key": "openrouter_api_key",
    },
    "openai": {
        "base_url": None,
        "key": "openai_api_key",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1/",
        "key": "groq_api_key",
    },
}
