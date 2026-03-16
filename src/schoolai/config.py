from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://schoolai:1234@localhost:5432/schoolai"

    # Telegram
    telegram_bot_token: str
    telegram_bot_token_dev: str = ""  # segundo token para pruebas (Modo Jornada dev)
    telegram_allowed_users: str = ""  # comma-separated user IDs

    # ── LLM model per skill (format: "provider/model") ────────────────────────
    llm_extractor: str = "zhipu/glm-4-flash"    # extractor JSON — rápido
    llm_chat:      str = "zhipu/glm-4.5-air"    # asistente IA — thinking model
    llm_router:    str = "zhipu/glm-4-flash"    # clasificador de mensajes

    # ── API keys por proveedor ─────────────────────────────────────────────────
    zhipu_api_key:      str = ""
    mistral_api_key:    str = ""
    deepseek_api_key:   str = ""
    moonshot_api_key:   str = ""
    nvidia_api_key:     str = ""
    minimax_api_key:    str = ""
    openrouter_api_key: str = ""
    openai_api_key:     str = ""

    # Groq — audio transcription (Whisper) + LLM opcional
    groq_api_key: str = ""

    # FastAPI
    api_host: str = "0.0.0.0"  # nosec B104 — intencional, uvicorn escucha en todas las interfaces
    api_port: int = 8000
    debug: bool = False

    # Redis (opcional — si no se configura, el estado vive sólo en RAM)
    redis_url: str = ""   # e.g. "redis://localhost:6379/0"

    # JWT / API auth
    jwt_secret_key: str = ""    # REQUIRED en producción — clave para firmar tokens
    jwt_expire_hours: int = 24  # tiempo de vida del token
    api_secret: str = ""        # clave compartida que el cliente usa para obtener un JWT

    # Logging
    log_dir: str = "logs"
    admin_telegram_id: int | None = None

    @property
    def allowed_user_ids(self) -> list[int]:
        if not self.telegram_allowed_users:
            return []
        return [int(uid.strip()) for uid in self.telegram_allowed_users.split(",") if uid.strip()]

    # ── Compat con código antiguo que aún use settings.glm_* ──────────────────
    @property
    def glm_api_key(self) -> str:
        return self.zhipu_api_key

    @property
    def glm_model(self) -> str:
        _, model = self.llm_chat.split("/", 1)
        return model

    @property
    def glm_extractor_model(self) -> str:
        _, model = self.llm_extractor.split("/", 1)
        return model


settings = Settings()
