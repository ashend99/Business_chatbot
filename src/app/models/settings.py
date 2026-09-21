"""Per-tenant settings, split by who is allowed to write them.

`TenantAdminSettings` is superadmin-only (set at onboarding, tenants read it
but never write it): things with cost/safety/billing implications or that
define the tenant's capability ceiling. `TenantSettings` is what the tenant
edits from the dashboard, always clamped by the admin ceiling -- see
services/settings_resolver.py, the only thing the bot reads through.

Both are strictly one-row-per-tenant, so `tenant_id` is the primary key
rather than using TenantScopedMixin's separate generated `id`.
"""

import uuid
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class BotTone(Enum):
    FORMAL = "formal"
    FRIENDLY = "friendly"
    CASUAL = "casual"


class NegotiationMode(Enum):
    FIXED = "fixed"
    ESCALATE = "escalate"


class OrderConfirmationMode(Enum):
    BOT = "bot"
    HUMAN = "human"


class TenantAdminSettings(TimestampMixin, Base):
    __tablename__ = "tenant_admin_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    # ISO 4217. Admin-only because Order stores bare numbers with no
    # currency -- a tenant changing it later would silently relabel history.
    currency_code: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    # capability ceiling: a tenant can switch these off in TenantSettings,
    # never on if the admin didn't grant them
    ordering_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    catalog_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    documents_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    leads_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    allowed_channels: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=lambda: ["website_widget", "facebook", "instagram", "whatsapp"],
        nullable=False,
    )
    # null = platform default (PROJECT_CONFIG.agent.model)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # stored only -- not enforced yet
    monthly_message_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_documents: Mapped[int | None] = mapped_column(Integer, nullable=True)


class TenantSettings(TimestampMixin, Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    # persona
    bot_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tone: Mapped[BotTone] = mapped_column(SAEnum(BotTone, name="bot_tone"), default=BotTone.FRIENDLY, nullable=False)
    language: Mapped[str] = mapped_column(String(50), default="English", nullable=False)
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # toggles (effective value = admin *_allowed AND this)
    bot_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ordering_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    catalog_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    documents_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    leads_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ordering rules
    delivery_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pickup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cash_on_delivery: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_order_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    negotiation_mode: Mapped[NegotiationMode] = mapped_column(
        SAEnum(NegotiationMode, name="negotiation_mode"), default=NegotiationMode.FIXED, nullable=False
    )
    order_confirmation_mode: Mapped[OrderConfirmationMode] = mapped_column(
        SAEnum(OrderConfirmationMode, name="order_confirmation_mode"),
        default=OrderConfirmationMode.BOT,
        nullable=False,
    )

    # notifications -- empty list = fall back to tenants.email
    notify_emails: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    notify_new_lead: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_new_order: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
