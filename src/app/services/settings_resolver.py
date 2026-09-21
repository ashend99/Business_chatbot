"""The single, read-only view of a tenant's settings that the bot, the
notifications and the dashboard consume.

Merges the two write-separated tables -- `TenantAdminSettings` (superadmin:
capability ceiling, currency, channels, model) and `TenantSettings` (tenant's
own choices) -- into one frozen `EffectiveSettings`, applying the rule that
an effective toggle = admin-allowed AND tenant-enabled: a tenant can switch
off what the admin granted, never switch on what wasn't.

Everything that runs per bot request goes through `get_effective_settings`
(small in-process TTL cache, invalidated on any settings write in this
process). Nothing here writes settings, and the bot must import only this
module -- never repos/settings*.py.
"""

import time
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.settings import (
    BotTone,
    NegotiationMode,
    OrderConfirmationMode,
    TenantAdminSettings,
    TenantSettings,
)
from app.repos import settings_read
from common import PROJECT_CONFIG

CACHE_TTL_SECONDS = 30
DEFAULT_CHANNELS = ("website_widget", "facebook", "instagram", "whatsapp")


@dataclass(frozen=True)
class EffectiveSettings:
    tenant_id: uuid.UUID

    # admin-owned
    currency_code: str
    allowed_channels: tuple[str, ...]
    llm_model: str
    monthly_message_limit: int | None
    max_documents: int | None

    # effective toggles (admin-allowed AND tenant-enabled)
    bot_enabled: bool
    ordering_enabled: bool
    catalog_enabled: bool
    documents_enabled: bool
    leads_enabled: bool

    # tenant-owned
    timezone: str
    bot_name: str | None
    tone: BotTone
    language: str
    welcome_message: str | None
    fallback_message: str | None
    custom_instructions: str | None
    delivery_enabled: bool
    pickup_enabled: bool
    cash_on_delivery: bool
    min_order_value: Decimal | None
    negotiation_mode: NegotiationMode
    order_confirmation_mode: OrderConfirmationMode
    notify_emails: tuple[str, ...]
    notify_new_lead: bool
    notify_new_order: bool

    @property
    def human_confirmation(self) -> bool:
        return self.order_confirmation_mode == OrderConfirmationMode.HUMAN

    @property
    def fulfillment_types(self) -> tuple[str, ...]:
        types = []
        if self.delivery_enabled:
            types.append("delivery")
        if self.pickup_enabled:
            types.append("pickup")
        return tuple(types)

    def recipients(self, tenant_email: str | None) -> list[str]:
        """Notification recipients: the tenant's configured list, or its
        signup email when none is configured."""
        if self.notify_emails:
            return list(self.notify_emails)
        return [tenant_email] if tenant_email else []


def _platform_default_model() -> str:
    return PROJECT_CONFIG.get("agent", {}).get("model", "gpt-4o-mini")


_cache: dict[uuid.UUID, tuple[float, EffectiveSettings]] = {}


def invalidate(tenant_id: uuid.UUID | None = None) -> None:
    """Drop a tenant's cached settings (or all) -- call after any settings
    write so the next request in this process sees it immediately."""
    if tenant_id is None:
        _cache.clear()
    else:
        _cache.pop(tenant_id, None)


async def _load(session: AsyncSession, tenant_id: uuid.UUID) -> EffectiveSettings:
    admin = await settings_read.get_admin_settings(session, tenant_id)
    tenant = await settings_read.get_tenant_settings(session, tenant_id)

    # Missing rows shouldn't happen (onboarding seeds both, the migration
    # backfilled existing tenants), but never crash a customer's chat over
    # it: fall back to the same defaults the columns declare.
    admin = admin or TenantAdminSettings(tenant_id=tenant_id, currency_code="USD")
    tenant = tenant or TenantSettings(tenant_id=tenant_id)

    def flag(model_value: bool | None, default: bool) -> bool:
        return default if model_value is None else model_value

    return EffectiveSettings(
        tenant_id=tenant_id,
        currency_code=(admin.currency_code or "USD").upper(),
        allowed_channels=tuple(admin.allowed_channels or DEFAULT_CHANNELS),
        llm_model=admin.llm_model or _platform_default_model(),
        monthly_message_limit=admin.monthly_message_limit,
        max_documents=admin.max_documents,
        bot_enabled=flag(tenant.bot_enabled, True),
        ordering_enabled=flag(admin.ordering_allowed, True) and flag(tenant.ordering_enabled, True),
        catalog_enabled=flag(admin.catalog_allowed, True) and flag(tenant.catalog_enabled, True),
        documents_enabled=flag(admin.documents_allowed, True) and flag(tenant.documents_enabled, True),
        leads_enabled=flag(admin.leads_allowed, True) and flag(tenant.leads_enabled, True),
        timezone=tenant.timezone or "UTC",
        bot_name=tenant.bot_name,
        tone=tenant.tone or BotTone.FRIENDLY,
        language=tenant.language or "English",
        welcome_message=tenant.welcome_message,
        fallback_message=tenant.fallback_message,
        custom_instructions=tenant.custom_instructions,
        delivery_enabled=flag(tenant.delivery_enabled, True),
        pickup_enabled=flag(tenant.pickup_enabled, True),
        cash_on_delivery=flag(tenant.cash_on_delivery, False),
        min_order_value=tenant.min_order_value,
        negotiation_mode=tenant.negotiation_mode or NegotiationMode.FIXED,
        order_confirmation_mode=tenant.order_confirmation_mode or OrderConfirmationMode.BOT,
        notify_emails=tuple(tenant.notify_emails or ()),
        notify_new_lead=flag(tenant.notify_new_lead, True),
        notify_new_order=flag(tenant.notify_new_order, True),
    )


async def get_effective_settings(
    tenant_id: uuid.UUID, session: AsyncSession | None = None
) -> EffectiveSettings:
    """Cached; pass `session` to reuse the caller's, otherwise a short-lived
    one is opened (tools run concurrently and can't share a session)."""
    cached = _cache.get(tenant_id)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]

    if session is not None:
        effective = await _load(session, tenant_id)
    else:
        async with AsyncSessionLocal() as own_session:
            effective = await _load(own_session, tenant_id)

    _cache[tenant_id] = (time.monotonic() + CACHE_TTL_SECONDS, effective)
    return effective
