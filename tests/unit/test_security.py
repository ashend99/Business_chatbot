from datetime import UTC, datetime, timedelta

import pytest
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_raw_token,
    hash_password,
    hash_token,
    verify_password,
    verify_superadmin_credentials,
)


def test_password_hash_round_trip() -> None:
    hashed = hash_password("correct horse")
    assert hashed != "correct horse"
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong horse", hashed)


def test_access_token_round_trip_and_expiry_claim() -> None:
    token = create_access_token({"sub": "abc", "scope": "tenant"}, expires_minutes=5)
    claims = decode_access_token(token)
    assert claims["sub"] == "abc"
    assert claims["scope"] == "tenant"
    expires = datetime.fromtimestamp(claims["exp"], tz=UTC)
    assert timedelta(minutes=4) < expires - datetime.now(UTC) <= timedelta(minutes=5)


def test_expired_token_is_rejected() -> None:
    token = create_access_token({"sub": "abc"}, expires_minutes=-1)
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = jwt.encode(
        {"sub": "abc", "scope": "platform_admin"},
        "not-the-secret",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(JWTError):
        decode_access_token(forged)


def test_raw_tokens_are_unique_and_hash_deterministically() -> None:
    a, b = generate_raw_token(), generate_raw_token()
    assert a != b
    assert len(a) >= 40
    assert hash_token(a) == hash_token(a)
    assert hash_token(a) != hash_token(b)
    assert a not in hash_token(a)


def test_superadmin_credentials() -> None:
    assert verify_superadmin_credentials(settings.superadmin_email, settings.superadmin_password)
    assert not verify_superadmin_credentials(settings.superadmin_email, "nope")
    assert not verify_superadmin_credentials("someone@example.com", settings.superadmin_password)
