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
    telegram_allowed_users: str = ""  # comma-separated user IDs

    # AI - GLM (Zhipu) — reserved for future skills
    glm_api_key: str = ""
    glm_model: str = "glm-4.7"

    # Groq - Audio transcription
    groq_api_key: str = ""

    # FastAPI
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    @property
    def allowed_user_ids(self) -> list[int]:
        if not self.telegram_allowed_users:
            return []
        return [int(uid.strip()) for uid in self.telegram_allowed_users.split(",") if uid.strip()]


settings = Settings()
