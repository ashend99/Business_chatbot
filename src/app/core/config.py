from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # local dev placeholder -- override via .env for your actual Postgres credentials
    database_url: str = "postgresql+psycopg://postgres:CHANGE_ME@localhost:5432/business_chatbot"
    bcrypt_rounds: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
