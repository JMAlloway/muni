from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import os

def _coerce_asyncpg_url(url: str) -> str:
    """Convert common Postgres URLs to asyncpg DSN for SQLAlchemy."""
    if not url:
        return url
    # Heroku provides postgres:// or postgresql://
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


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
    # Optional here to allow Heroku-style DATABASE_URL fallback.
    DB_URL: Optional[str] = None  # resolved at runtime if missing

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
    # Deployment / hosting
    # ------------------------------------------------------------------
    PUBLIC_APP_HOST: Optional[str] = None  # e.g., "www.easyrfp.ai" (no scheme)
    START_SCHEDULER_WEB: bool = False      # start APScheduler in web dyno (default off)
    RUN_DDL_ON_START: bool = True          # run create_all on startup (disable in prod)

    # ------------------------------------------------------------------
    # Model configuration
    # ------------------------------------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # ignore any unrecognized vars instead of erroring
    )

    # ------------------------------------------------------------------
    # Storage (S3 / R2 / Local)
    # ------------------------------------------------------------------
    DOCS_BUCKET: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"  # R2 accepts 'auto' as well
    S3_ADDRESSING_STYLE: str = "virtual"  # or 'path'
    LOCAL_UPLOAD_DIR: str = "uploads"


# create global settings instance and normalize DB URL
settings = Settings()

# Fallback: allow DATABASE_URL and coerce to asyncpg
if not settings.DB_URL:
    fallback = os.getenv("DATABASE_URL", "")
    if fallback:
        settings.DB_URL = _coerce_asyncpg_url(fallback)

# Also coerce explicit DB_URL if it was provided in sync form
if settings.DB_URL:
    settings.DB_URL = _coerce_asyncpg_url(settings.DB_URL)
