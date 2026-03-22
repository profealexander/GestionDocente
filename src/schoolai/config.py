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
    database_url: str = "postgresql+asyncpg://schoolai:1234@localhost:5432/schoolai"

    @field_validator("database_url", mode="before")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        """Railway provee postgres:// — asyncpg requiere postgresql+asyncpg://"""
        if v.startswith("postgres://"):
            v = "postgresql+asyncpg://" + v[len("postgres://"):]
        elif v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v

    # Telegram
    telegram_bot_token: str
    telegram_bot_token_dev: str = ""  # segundo token para pruebas (Modo Jornada dev)
    telegram_allowed_users: str = ""  # comma-separated user IDs

    # ── LLM model per skill (format: "provider/model") ────────────────────────
    llm_extractor: str = "groq/llama-3.1-8b-instant"   # extractor JSON — rápido
    llm_chat:      str = "groq/llama-3.3-70b-versatile" # asistente IA
    llm_router:    str = "groq/llama-3.1-8b-instant"   # clasificador de mensajes

    # ── API keys ───────────────────────────────────────────────────────────────
    groq_api_key: str = ""  # Groq — transcripción Whisper + LLM extractor/chat

    # FastAPI
    api_host: str = "0.0.0.0"  # nosec B104 — intencional, uvicorn escucha en todas las interfaces
    api_port: int = 8000
    port: int = 0  # Railway inyecta PORT — si está presente, tiene prioridad sobre api_port

    @property
    def effective_api_port(self) -> int:
        return self.port if self.port else self.api_port
    debug: bool = False

    # Redis (opcional — si no se configura, el estado vive sólo en RAM)
    redis_url: str = ""   # e.g. "redis://localhost:6379/0"

    # JWT / API auth
    jwt_secret_key: str = ""    # REQUIRED en producción — clave para firmar tokens
    jwt_expire_hours: int = 24  # tiempo de vida del token
    api_secret: str = ""        # clave compartida que el cliente usa para obtener un JWT

    # WhatsApp — Green API
    green_api_instance: str = ""   # idInstance, e.g. "1101234567"
    green_api_token:    str = ""   # apiTokenInstance

    # Logging
    log_dir: str = "logs"
    admin_telegram_id: int | None = None

    @property
    def allowed_user_ids(self) -> list[int]:
        if not self.telegram_allowed_users:
            return []
        return [int(uid.strip()) for uid in self.telegram_allowed_users.split(",") if uid.strip()]

settings = Settings()
