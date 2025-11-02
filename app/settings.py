from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = "local"

    # auth/session config
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRES_MIN: int = 120

    # database
    DB_URL: str  # required

    # email / SMTP
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "alerts@example.local"

    # optional auth for SMTP servers like Mailtrap, SES, Gmail, etc.
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None

    # scheduler config
    DIGEST_SEND_HOUR: int = 7
    TIMEZONE: str = "America/New_York"

    # bootstrap admin
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "changeme"

    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
    }

settings = Settings()
