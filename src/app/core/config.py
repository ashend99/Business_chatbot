from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# below this a JWT signing secret is guessable enough to forge tokens
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # "development" (local, the default), "staging" (the deployed dev branch)
    # or "production". Any deployed environment refuses to start with dev
    # placeholder secrets still in place -- see _check_deployed.
    environment: str = "development"

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

    # documents module (Phase 2) -- secret + schema-pinned values stay here;
    # everything else (embedding model, batch/retry tuning, chunking sizes,
    # upload limits) lives in project_config.yaml (see PROJECT_CONFIG)
    openai_api_key: str = "CHANGE_ME"
    # must match the pgvector column width set at migration time
    # (database/alembic/versions/e6b32ddcbecb_add_documents_module.py) --
    # not freely tunable via project_config.yaml since changing it without a
    # matching migration would break embedding inserts
    embedding_dimensions: int = 1536

    # error reporting -- unset (the default) disables Sentry entirely
    sentry_dsn: str | None = None
    # fraction of requests traced for performance; errors are always sent
    sentry_traces_sample_rate: float = 0.05

    @model_validator(mode="after")
    def _check_deployed(self) -> "Settings":
        """Fail fast at startup instead of running on a public URL with a
        forgeable JWT secret or a default superadmin password. Production
        additionally needs real email -- the console backend silently drops
        onboarding invites; staging may keep it."""
        if self.environment == "development":
            return self
        problems = []
        if "CHANGE_ME" in self.jwt_secret or len(self.jwt_secret) < MIN_JWT_SECRET_LENGTH:
            problems.append(f"JWT_SECRET must be a random value of at least {MIN_JWT_SECRET_LENGTH} characters")
        if "CHANGE_ME" in self.superadmin_password:
            problems.append("SUPERADMIN_PASSWORD is still the placeholder")
        if "CHANGE_ME" in self.openai_api_key:
            problems.append("OPENAI_API_KEY is not set")
        if "CHANGE_ME" in self.database_url:
            problems.append("DATABASE_URL is not set")
        if self.environment == "production" and self.email_backend != "smtp":
            problems.append("EMAIL_BACKEND must be 'smtp' (console only logs emails)")
        if problems:
            raise ValueError(f"unsafe {self.environment} configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
