"""Deployed environments (staging, production) refuse to start with dev
placeholders; production also requires real email."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

SAFE = {
    "environment": "production",
    "database_url": "postgresql+psycopg://app:secret@db.example.com:6543/postgres",
    "jwt_secret": "x" * 48,
    "superadmin_password": "a-real-password",
    "openai_api_key": "sk-real",
    "email_backend": "smtp",
}


def make(**overrides) -> Settings:
    # _env_file=None: judge only what's passed, not the developer's .env
    return Settings(_env_file=None, **{**SAFE, **overrides})


def test_safe_production_config_is_accepted() -> None:
    assert make().environment == "production"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"jwt_secret": "CHANGE_ME_DEV_SECRET"}, "JWT_SECRET"),
        ({"jwt_secret": "short"}, "JWT_SECRET"),
        ({"superadmin_password": "CHANGE_ME"}, "SUPERADMIN_PASSWORD"),
        ({"openai_api_key": "CHANGE_ME"}, "OPENAI_API_KEY"),
        ({"database_url": "postgresql+psycopg://postgres:CHANGE_ME@localhost/x"}, "DATABASE_URL"),
        ({"email_backend": "console"}, "EMAIL_BACKEND"),
    ],
)
def test_unsafe_production_config_is_rejected(override: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        make(**override)


@pytest.mark.parametrize(
    "override",
    [
        {"jwt_secret": "short"},
        {"superadmin_password": "CHANGE_ME"},
        {"openai_api_key": "CHANGE_ME"},
    ],
)
def test_staging_also_rejects_placeholder_secrets(override: dict) -> None:
    """The deployed dev branch is on a public URL too."""
    with pytest.raises(ValidationError, match="unsafe staging configuration"):
        make(environment="staging", **override)


def test_staging_may_use_console_email() -> None:
    assert make(environment="staging", email_backend="console").email_backend == "console"


def test_development_allows_placeholders() -> None:
    dev = make(
        environment="development", jwt_secret="CHANGE_ME_DEV_SECRET", email_backend="console"
    )
    assert dev.jwt_secret == "CHANGE_ME_DEV_SECRET"
