from functools import cached_property

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = ""  # REQUIRED — set via DATABASE_URL env var

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        """Railway provee postgres:// — asyncpg requiere postgresql+asyncpg://"""
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://") :]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        return v

    # Telegram
    telegram_bot_token: str
    telegram_bot_token_jornada: str = ""  # segundo token — Modo Jornada
    telegram_bot_token_agente: str = ""  # tercer token — Bot Agente (GLM directo)
    telegram_allowed_users: str = ""  # comma-separated user IDs

    # ── LLM model per skill (format: "provider/model") ────────────────────────
    # Scores: benchmark 2026-04-23 (classifier 40% · planner 35% · synthesizer 25%)
    llm_extractor: str = "mistral/mistral-medium-latest"       # legado v1 — mismo que llm_router
    llm_chat: str = "groq/compound-beta"                       # chat general — búsqueda web nativa
    llm_chat_fallback: str = "mistral/mistral-small-latest"    # fallback chat
    llm_vision: str = "openrouter/nvidia/nemotron-nano-12b-v2-vl:free"  # visión — 128K ctx, free
    llm_vision_fallback: str = "openrouter/google/gemma-4-31b-it:free"  # visión fallback — free

    # CLASSIFIER — gateway/router.py: clasifica intent en JSON (domain, intent, entities)
    # #4 classifier 86.4% — 100% noex, sin límite RPM, estable
    llm_router: str = "mistral/mistral-medium-latest"
    # #3 classifier 87.1% — 100% noex, paid
    llm_router_fallback: str = "deepseek/deepseek-reasoner"

    # SYNTHESIZER — agent/synthesizer.py: redacta respuesta final en español
    # #2 synthesizer 94.4% — 694ms TTFT, español 100%, Groq free (20 RPM)
    llm_synthesizer: str = "groq/meta-llama/llama-4-scout-17b-16e-instruct"
    # free (ollama cloud) → paid (mistral small)
    llm_synthesizer_fallback: str = (
        "ollama/gemini-3-flash-preview:cloud,mistral/mistral-small-latest"
    )

    # PLANNER — agent/planner.py: genera plan JSON [{tool, params}]
    # #1 planner 94.6% — 437ms, JSON perfecto, Groq free (20 RPM, cuota distinta a synthesizer)
    llm_planner: str = "groq/openai/gpt-oss-120b"
    # free (ollama cloud) → paid (deepseek reasoner)
    llm_planner_fallback: str = (
        "ollama/gemini-3-flash-preview:cloud,deepseek/deepseek-reasoner"
    )

    llm_context_agent: str = "mistral/mistral-small-latest"    # context skill agent

    # ── API keys ───────────────────────────────────────────────────────────────
    groq_api_key: str = ""  # Groq — Whisper + fallback LLM
    zhipu_api_key: str = ""  # ZhipuAI China endpoint (legacy)
    zai_api_key: str = ""  # Z.AI global endpoint — GLM-4.7-Flash orquestador
    google_api_key: str = ""  # Google AI Studio — Gemini/Gemma models (multimodal extractor)
    mistral_api_key: str = ""  # Mistral — extractor + router + chat fallback (benchmark 2026-04-21)
    deepseek_api_key: str = ""
    moonshot_api_key: str = ""
    nvidia_api_key: str = ""
    minimax_api_key: str = ""
    openrouter_api_key: str = ""
    kilo_api_key: str = ""  # Kilo AI Gateway — OpenAI-compat, free tier
    hf_token: str = ""      # HuggingFace Inference Providers (router.huggingface.co)
    openai_api_key: str = ""
    ollama_api_key: str = "ollama"  # OpenAI client requiere un valor; Ollama local suele ignorarlo
    ollama_base_url: str = "http://127.0.0.1:11434/v1/"  # endpoint OpenAI-compatible

    # FastAPI
    api_host: str = "0.0.0.0"  # nosec B104 — intencional, uvicorn escucha en todas las interfaces
    api_port: int = 8000
    port: int = 0  # Railway inyecta PORT — si está presente, tiene prioridad sobre api_port
    # CORS — en producción establecer con el dominio exacto de la PWA, e.g.:
    # CORS_ORIGINS=https://schoolai-web.pages.dev
    cors_origins: str = (
        "http://localhost:3000,http://localhost:5173"  # desarrollo; dominio exacto en producción
    )

    @property
    def effective_api_port(self) -> int:
        return self.port or self.api_port

    debug: bool = False

    # Redis (opcional — si no se configura, el estado vive sólo en RAM)
    redis_url: str = ""  # e.g. "redis://localhost:6379/0"

    # JWT / API auth
    jwt_secret_key: str = ""  # REQUIRED en producción — clave para firmar tokens
    jwt_expire_hours: int = 24  # tiempo de vida del token
    api_secret: str = ""  # clave compartida que el cliente usa para obtener un JWT

    # WhatsApp — Green API
    green_api_instance: str = ""  # idInstance, e.g. "1101234567"
    green_api_token: str = ""  # apiTokenInstance

    # Logging
    log_dir: str = "logs"
    admin_telegram_id: int | None = None

    # Zona horaria de la institución (IANA name, e.g. "America/Guayaquil")
    school_timezone: str = "America/Guayaquil"

    # Autonomía: si True, el bot pide confirmación antes de toda escritura en DB
    supervised_mode: bool = False

    # Gateway v2 — cuando True los bots normalizan a TaskSpec antes del dispatch v1
    gateway_enabled: bool = False
    gateway_url: str = "http://localhost:8001"  # usado por canales externos (web, CLI)

    @cached_property
    def allowed_user_ids(self) -> list[int]:
        if not self.telegram_allowed_users:
            return []
        return [int(uid.strip()) for uid in self.telegram_allowed_users.split(",") if uid.strip()]


settings = Settings()
