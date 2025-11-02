from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------------
    ENV: str = "local"

    # ------------------------------------------------------------------
    # Auth/session
    # ------------------------------------------------------------------
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRES_MIN: int = 120

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DB_URL: str  # required

    # ------------------------------------------------------------------
    # Email / SMTP
    # ------------------------------------------------------------------
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "alerts@example.local"
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # ------------------------------------------------------------------
    # Scheduler / digest config
    # ------------------------------------------------------------------
    DIGEST_SEND_HOUR: int = 7
    TIMEZONE: str = "America/New_York"

    # ------------------------------------------------------------------
    # Bootstrap admin
    # ------------------------------------------------------------------
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "changeme"

    # ------------------------------------------------------------------
    # AI / LLM configuration
    # ------------------------------------------------------------------
    ai_provider: Optional[str] = None          # e.g. "ollama" or "openai"
    ollama_model: str = "llama3"               # default local model name
    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: Optional[str] = None       # optional hosted key

    # ------------------------------------------------------------------
    # Model configuration
    # ------------------------------------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # ignore any unrecognized vars instead of erroring
    )


# create global settings instance
settings = Settings()
