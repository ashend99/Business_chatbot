"""services/settings_resolver.py against real rows: the merge rule
(effective = admin allowed AND tenant enabled), defaults, and the cache."""

import pytest
from factories import make_tenant

from app.models.settings import TenantAdminSettings, TenantSettings
from app.repos import tenants as tenants_repo
from app.services import settings_resolver
from app.services.settings_resolver import get_effective_settings


@pytest.mark.parametrize(
    ("admin_allowed", "tenant_enabled", "effective"),
    [(True, True, True), (True, False, False), (False, True, False), (False, False, False)],
)
@pytest.mark.parametrize("feature", ["ordering", "catalog", "documents", "leads"])
async def test_effective_toggle_is_admin_and_tenant(
    session, feature, admin_allowed, tenant_enabled, effective
) -> None:
    tenant = await make_tenant(
        session,
        admin={f"{feature}_allowed": admin_allowed},
        settings={f"{feature}_enabled": tenant_enabled},
    )
    settings = await get_effective_settings(tenant.id, session)
    assert getattr(settings, f"{feature}_enabled") is effective


async def test_admin_and_tenant_fields_are_merged(session) -> None:
    tenant = await make_tenant(
        session,
        currency_code="lkr",
        timezone="Asia/Colombo",
        admin={
            "allowed_channels": ["whatsapp"],
            "llm_model": "gpt-4o",
            "monthly_message_limit": 500,
        },
        settings={
            "bot_name": "Sunny",
            "notify_emails": ["ops@example.com"],
            "pickup_enabled": False,
        },
    )
    settings = await get_effective_settings(tenant.id, session)
    assert settings.currency_code == "LKR"
    assert settings.allowed_channels == ("whatsapp",)
    assert settings.llm_model == "gpt-4o"
    assert settings.monthly_message_limit == 500
    assert settings.timezone == "Asia/Colombo"
    assert settings.bot_name == "Sunny"
    assert settings.notify_emails == ("ops@example.com",)
    assert settings.fulfillment_types == ("delivery",)


async def test_llm_model_defaults_to_platform_model(session) -> None:
    tenant = await make_tenant(session)
    assert (await get_effective_settings(tenant.id, session)).llm_model == "gpt-4o-mini"


async def test_missing_settings_rows_fall_back_to_defaults(session) -> None:
    tenant = await tenants_repo.create_tenant(session, name="Bare", slug="bare-tenant")
    await session.commit()
    settings = await get_effective_settings(tenant.id, session)
    assert settings.currency_code == "USD"
    assert settings.bot_enabled and settings.ordering_enabled
    assert settings.allowed_channels == settings_resolver.DEFAULT_CHANNELS


async def test_opens_its_own_session_when_none_given(session) -> None:
    tenant = await make_tenant(session, currency_code="EUR")
    assert (await get_effective_settings(tenant.id)).currency_code == "EUR"


async def test_results_are_cached_until_invalidated(session) -> None:
    tenant = await make_tenant(session)
    assert (await get_effective_settings(tenant.id, session)).bot_name is None

    row = await session.get(TenantSettings, tenant.id)
    row.bot_name = "Changed"
    admin = await session.get(TenantAdminSettings, tenant.id)
    admin.currency_code = "GBP"
    await session.commit()

    stale = await get_effective_settings(tenant.id, session)
    assert stale.bot_name is None and stale.currency_code == "USD"

    settings_resolver.invalidate(tenant.id)
    fresh = await get_effective_settings(tenant.id, session)
    assert fresh.bot_name == "Changed" and fresh.currency_code == "GBP"


async def test_cache_expires_after_ttl(session, monkeypatch) -> None:
    tenant = await make_tenant(session)
    await get_effective_settings(tenant.id, session)
    row = await session.get(TenantSettings, tenant.id)
    row.language = "Tamil"
    await session.commit()

    clock = settings_resolver.time.monotonic() + settings_resolver.CACHE_TTL_SECONDS + 1
    monkeypatch.setattr(settings_resolver.time, "monotonic", lambda: clock)
    assert (await get_effective_settings(tenant.id, session)).language == "Tamil"
