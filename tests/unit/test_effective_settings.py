"""EffectiveSettings' derived properties (the DB-backed merge rule is in
tests/db/test_settings_resolver.py)."""

from fakes import effective_settings

from app.models.settings import OrderConfirmationMode


def test_fulfillment_types() -> None:
    assert effective_settings().fulfillment_types == ("delivery", "pickup")
    assert effective_settings(delivery_enabled=False).fulfillment_types == ("pickup",)
    assert effective_settings(pickup_enabled=False).fulfillment_types == ("delivery",)
    assert effective_settings(delivery_enabled=False, pickup_enabled=False).fulfillment_types == ()


def test_human_confirmation_flag() -> None:
    assert not effective_settings().human_confirmation
    assert effective_settings(
        order_confirmation_mode=OrderConfirmationMode.HUMAN
    ).human_confirmation


def test_recipients_prefers_configured_list() -> None:
    settings = effective_settings(notify_emails=("a@example.com", "b@example.com"))
    assert settings.recipients("owner@example.com") == ["a@example.com", "b@example.com"]


def test_recipients_falls_back_to_tenant_email() -> None:
    assert effective_settings().recipients("owner@example.com") == ["owner@example.com"]
    assert effective_settings().recipients(None) == []
