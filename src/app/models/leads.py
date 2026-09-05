import uuid
from enum import Enum

from sqlalchemy import Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class LeadStatus(Enum):
    NEW = "new"
    INTERESTED = "interested"


class Lead(TenantScopedMixin, Base):
    """Minimal write-only lead capture for the bot's `create_lead` tool
    (Phase 4). Not the full Phase 5 module -- no dashboard list/update flows
    yet, and `fields` is intentionally schema-free (JSONB) since the real
    per-tenant configurable field set is Phase 5 scope."""

    __tablename__ = "leads"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    matched_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("variants.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[LeadStatus] = mapped_column(SAEnum(LeadStatus, name="lead_status"), nullable=False)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
