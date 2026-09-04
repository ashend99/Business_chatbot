from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # local dev placeholder -- override via .env for your actual Postgres credentials
    database_url: str = "postgresql+psycopg://postgres:CHANGE_ME@localhost:5432/business_chatbot"
    bcrypt_rounds: int = 12

    jwt_secret: str = "CHANGE_ME_DEV_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # env-configured superadmin credentials -- no platform_admins table for MVP
    superadmin_email: str = "admin@example.com"
    superadmin_password: str = "CHANGE_ME"

    email_backend: str = "console"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "no-reply@example.com"
    smtp_use_tls: bool = True

    # documents module (Phase 2) -- embeddings + upload bounds
    openai_api_key: str = "CHANGE_ME"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    max_document_upload_mb: int = 10
    max_document_chars: int = 200_000


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
