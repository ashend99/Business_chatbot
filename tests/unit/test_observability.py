"""Sentry is off without a DSN and never ships customer data when on."""

from app.core import observability
from app.core.config import Settings


def test_sentry_disabled_without_dsn(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(observability.sentry_sdk, "init", lambda **kw: calls.append(kw))
    assert observability.init_sentry(Settings(_env_file=None, sentry_dsn=None)) is False
    assert calls == []


def test_sentry_never_sends_personal_data(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(observability.sentry_sdk, "init", lambda **kw: calls.append(kw))
    settings = Settings(_env_file=None, sentry_dsn="https://key@example.ingest.sentry.io/1")
    assert observability.init_sentry(settings) is True
    [options] = calls
    assert options["send_default_pii"] is False
    assert options["max_request_body_size"] == "never"
    assert options["include_local_variables"] is False
    assert options["environment"] == settings.environment
