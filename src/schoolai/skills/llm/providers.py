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
    # Google Gemini — OpenAI-compatible endpoint (requiere GOOGLE_API_KEY)
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key": "google_api_key",
    },
    # Ollama — cloud (https://ollama.com) o local (http://localhost:11434)
    # Cloud: usa modelo "qwen3-coder:480b-cloud" y CLI auth automática si está signin
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "key": "ollama_api_key",
    },
    # HuggingFace Inference Providers — router unificado (nscale, cerebras, sambanova, novita…)
    # Modelo con provider específico: extra_body={"provider": "nscale"}
    # Benchmark 2026-04-21: Qwen3-32B/nscale #4 91.1% (803ms, 254t/s)
    "huggingface": {
        "base_url": "https://router.huggingface.co/v1/",
        "key": "hf_token",
    },
}
