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
    llm_extractor: str = "google/gemini-3.1-flash-lite-preview"  # extracción estructurada — 990ms, 100% JSON noex, 500 RPD free
    llm_chat: str = "groq/compound-beta"  # chat general — búsqueda web nativa, 70K TPM
    llm_chat_fallback: str = "groq/qwen/qwen3-32b"  # fallback chat — 1038ms, 100% JSON noex, gratis
    llm_vision: str = "openrouter/nvidia/nemotron-nano-12b-v2-vl:free"  # visión — 128K ctx, free
    llm_vision_fallback: str = "openrouter/google/gemma-4-31b-it:free"  # visión fallback — free
    llm_router: str = "google/gemini-3.1-flash-lite-preview"  # routing / clasificación — 100% JSON noex, 500 RPD free
    llm_router_fallback: str = "groq/openai/gpt-oss-120b,deepseek/deepseek-chat"  # 457ms 100% JSON → 3069ms 100% JSON
    llm_orchestrator: str = "groq/qwen/qwen3-32b"  # 1092ms, 100% JSON noex, gratis Groq — benchmark 2026-04-19
    llm_orchestrator_fallback: str = "google/gemini-3.1-flash-lite-preview,deepseek/deepseek-chat,mistral/mistral-medium-latest"  # 100% JSON noex → fallback seguro
    llm_context_agent: str = "groq/qwen/qwen3-32b"  # context skill agent — mismo tier que orchestrator, configurable independientemente

    # ── API keys ───────────────────────────────────────────────────────────────
    groq_api_key: str = ""  # Groq — Whisper + fallback LLM
    zhipu_api_key: str = ""  # ZhipuAI China endpoint (legacy)
    zai_api_key: str = ""  # Z.AI global endpoint — GLM-4.7-Flash orquestador
    google_api_key: str = ""  # Google AI Studio — Gemini models
    mistral_api_key: str = ""  # Mistral — chat general + orquestación
    deepseek_api_key: str = ""
    moonshot_api_key: str = ""
    nvidia_api_key: str = ""
    minimax_api_key: str = ""
    openrouter_api_key: str = ""
    kilo_api_key: str = ""  # Kilo AI Gateway — OpenAI-compat, free tier
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
