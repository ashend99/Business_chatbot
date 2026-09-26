"""Test-data builders. Each one writes real rows through the app's own repo
functions (so the data looks exactly like production data) and commits.

The catalog is a deliberately generic small shop -- per AGENTS.md, test data
must not encode any one real tenant's business.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.catalog import Category, StockStatus, Variant
from app.models.conversations import Conversation, ConversationChannel, MessageRole
from app.models.leads import LeadFieldType
from app.models.settings import TenantSettings
from app.models.tenants import ApiKeyTypes, Tenant
from app.repos import catalog as catalog_repo
from app.repos import conversations as conversations_repo
from app.repos import leads_admin as leads_admin_repo
from app.repos import settings_admin as settings_admin_repo
from app.repos import tenants as tenants_repo


async def make_tenant(
    session: AsyncSession,
    *,
    name: str = "Test Shop",
    currency_code: str = "USD",
    timezone: str = "UTC",
    admin: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    seed_lead_fields: bool = True,
    is_active: bool = True,
) -> Tenant:
    """A fully onboarded tenant: both settings rows, and (by default) the
    standard name/phone(required)/email lead fields. `admin` overrides
    TenantAdminSettings columns, `settings` overrides TenantSettings columns."""
    suffix = uuid.uuid4().hex[:8]
    tenant = await tenants_repo.create_tenant(
        session, name=name, slug=f"test-shop-{suffix}", email=f"owner-{suffix}@example.com"
    )
    await settings_admin_repo.create_default_settings(
        session, tenant.id, currency_code=currency_code, timezone=timezone, **(admin or {})
    )
    if settings:
        row = await session.get(TenantSettings, tenant.id)
        for key, value in settings.items():
            setattr(row, key, value)
    if seed_lead_fields:
        await leads_admin_repo.seed_default_lead_field_defs(session, tenant.id)
    tenant.is_active = is_active
    await session.commit()
    return tenant


async def set_lead_fields(
    session: AsyncSession, tenant_id: uuid.UUID, fields: list[tuple[str, bool]]
) -> None:
    """Replace a tenant's lead-capture schema with (field_key, required) pairs."""
    await leads_admin_repo.replace_lead_field_defs(
        session,
        tenant_id,
        [
            {
                "field_key": key,
                "label": key.replace("_", " ").title(),
                "field_type": LeadFieldType.TEXT,
                "required": required,
            }
            for key, required in fields
        ],
    )
    await session.commit()


async def make_api_key(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    """Returns the raw api_secret key for X-Api-Key."""
    _key, raw = await tenants_repo.create_api_key(
        session, tenant_id=tenant_id, key_type=ApiKeyTypes.API_SECRET
    )
    await session.commit()
    return raw


async def make_conversation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    external_user_id: str | None = None,
    channel: ConversationChannel = ConversationChannel.WEBSITE_WIDGET,
) -> Conversation:
    conversation = await conversations_repo.get_or_create_conversation(
        session, tenant_id, channel, external_user_id or f"visitor-{uuid.uuid4().hex[:8]}"
    )
    await session.commit()
    return conversation


async def add_messages(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    messages: list[tuple[MessageRole, str]],
) -> None:
    """Add a transcript with one second between messages. Back-to-back
    add_message calls can land on the same clock tick, and transcripts are
    ordered by created_at alone, so tests pin the timestamps."""
    start = datetime.now(UTC) - timedelta(minutes=len(messages))
    for i, (role, content) in enumerate(messages):
        message = await conversations_repo.add_message(
            session, tenant_id, conversation_id, role, content
        )
        message.created_at = start + timedelta(seconds=i)
    await session.commit()


@dataclass
class Catalog:
    beverages: Category
    hot_drinks: Category
    cold_drinks: Category
    bakery: Category
    latte_small: Variant
    latte_large: Variant
    iced_tea: Variant
    cake_slice: Variant
    cake_whole: Variant
    muffin_sold_out: Variant
    retired_item: Variant


async def make_catalog(session: AsyncSession, tenant_id: uuid.UUID) -> Catalog:
    """Beverages > (Hot Drinks, Cold Drinks) and Bakery, with multi-variant,
    single-variant, out-of-stock and inactive items. Beverages itself holds
    no products directly -- exercises browse_catalog's subtree expansion."""
    beverages = await catalog_repo.create_category(session, tenant_id, name="Beverages")
    hot = await catalog_repo.create_category(
        session, tenant_id, name="Hot Drinks", parent_id=beverages.id
    )
    cold = await catalog_repo.create_category(
        session, tenant_id, name="Cold Drinks", parent_id=beverages.id
    )
    bakery = await catalog_repo.create_category(session, tenant_id, name="Bakery")

    latte = await catalog_repo.create_product(
        session,
        tenant_id,
        name="Classic Latte",
        category_id=hot.id,
        variants=[
            {"name": "Small", "price": Decimal("3.50"), "stock_status": StockStatus.UNLIMITED},
            {"name": "Large", "price": Decimal("4.50"), "stock_status": StockStatus.UNLIMITED},
        ],
    )
    iced_tea = await catalog_repo.create_product(
        session,
        tenant_id,
        name="Iced Tea",
        category_id=cold.id,
        variants=[{"price": Decimal("2.75"), "stock_qty": 12}],
    )
    cake = await catalog_repo.create_product(
        session,
        tenant_id,
        name="Chocolate Cake",
        category_id=bakery.id,
        variants=[
            {"name": "Slice", "price": Decimal("4.00")},
            {"name": "Whole", "price": Decimal("30.00")},
        ],
    )
    muffin = await catalog_repo.create_product(
        session,
        tenant_id,
        name="Blueberry Muffin",
        category_id=bakery.id,
        variants=[
            {
                "price": Decimal("2.50"),
                "stock_status": StockStatus.OUT_OF_STOCK,
                "stock_message": "back tomorrow",
            }
        ],
    )
    retired = await catalog_repo.create_product(
        session,
        tenant_id,
        name="Retired Scone",
        category_id=bakery.id,
        variants=[{"price": Decimal("2.00")}],
    )

    async def variants_of(product_id: uuid.UUID) -> dict[str, Variant]:
        return {
            v.name: v
            for v in await catalog_repo.list_variants_for_product(session, tenant_id, product_id)
        }

    latte_v = await variants_of(latte.id)
    cake_v = await variants_of(cake.id)
    retired_v = (await variants_of(retired.id))["Retired Scone"]
    retired_v.active = False
    await session.commit()

    return Catalog(
        beverages=beverages,
        hot_drinks=hot,
        cold_drinks=cold,
        bakery=bakery,
        latte_small=latte_v["Small"],
        latte_large=latte_v["Large"],
        iced_tea=(await variants_of(iced_tea.id))["Iced Tea"],
        cake_slice=cake_v["Slice"],
        cake_whole=cake_v["Whole"],
        muffin_sold_out=(await variants_of(muffin.id))["Blueberry Muffin"],
        retired_item=retired_v,
    )


def tenant_headers(tenant_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token({"sub": str(tenant_id), "scope": "tenant"})
    return {"Authorization": f"Bearer {token}"}


def superadmin_headers() -> dict[str, str]:
    token = create_access_token({"sub": "superadmin", "scope": "platform_admin"})
    return {"Authorization": f"Bearer {token}"}
