from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: SecretStr
    DB_NAME: str

    JWT_SECRET_KEY: SecretStr
    OPENAI_API_KEY: SecretStr
    AI_RECIPE_MODEL: str = "gpt-5-nano"

    REDIS_URL: str = "redis://localhost:6379/0"

    WITHDRAWAL_GRACE_DAYS: int = 7

    EMAIL_BACKEND: str = "smtp"  # console | smtp
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_FROM_NAME: str = "삭삭"
    SMTP_USE_TLS: bool = True

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD.get_secret_value()}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def database_rag_sync_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD.get_secret_value()}"
            f"@{self.DB_HOST}:{self.DB_PORT}/saksak_rag"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
