import uuid
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class LeadStatus(Enum):
    INTERESTED = "interested"
    NEW = "new"
    CONTACTED = "contacted"
    CONVERTED = "converted"
    LOST = "lost"


class LeadFieldType(Enum):
    TEXT = "text"
    PHONE = "phone"
    EMAIL = "email"
    DATE = "date"
    TEXTAREA = "textarea"


class LeadFieldDef(TenantScopedMixin, Base):
    """Per-tenant configurable lead capture schema -- what the bot should
    ask for, and what `Lead.fields`' keys mean. Seeded with sensible
    defaults (name/phone/email) at onboarding; clients edit/add/remove
    from the dashboard."""

    __tablename__ = "lead_field_defs"

    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    field_type: Mapped[LeadFieldType] = mapped_column(SAEnum(LeadFieldType, name="lead_field_type"), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Lead(TenantScopedMixin, Base):
    """`repos/leads.py`'s create_or_update_lead_from_bot is the only way
    this table is written from the chat pipeline -- `repos/leads_admin.py`
    is the separate read/update surface for the dashboard. Keep that
    import boundary: the /bot router (and anything it imports) must never
    reach into leads_admin.

    `fields` holds `{field_key: value}` per LeadFieldDef -- named `fields`
    rather than the plan's `field_values` since that's what shipped in the
    original Phase 4 migration; renaming now would just be churn.
    """

    __tablename__ = "leads"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    matched_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("variants.id", ondelete="SET NULL"), nullable=True
    )
    # the bot only ever writes INTERESTED/NEW; CONTACTED/CONVERTED/LOST are
    # set manually from the dashboard
    status: Mapped[LeadStatus] = mapped_column(SAEnum(LeadStatus, name="lead_status"), nullable=False)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # manually entered on conversion -- feeds the future Sales module
    deal_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
