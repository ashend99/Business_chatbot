from decimal import Decimal
from enum import Enum
import uuid

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class OrderStatus(Enum):
    DRAFT = "draft"
    PLACED = "placed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Order(TenantScopedMixin, Base):
    """A cart the bot agent builds and confirms on a customer's behalf --
    everything up through `PLACED` is the agent's job; payment and
    fulfillment past that point are a human/off-platform step this table
    never models. Deliberately separate from `Lead` (see the leads/orders
    design discussion): `Lead` is a sales-pipeline record (is this person
    worth following up with) that doesn't require a cart, while `Order` is
    a fulfillment-pipeline record (what was agreed, has it shipped) that
    doesn't require a name/phone yet -- `lead_id` links them once both
    exist for the same conversation, attached automatically by
    repos/orders.py rather than managed by the agent.

    `items` is a frozen snapshot per line -- product name, variant label,
    quantity, and the *unit_price at order time* -- copied out of the
    catalog rather than joined live, so a later catalog price change never
    silently rewrites a past order. `total` is likewise computed
    server-side from real catalog prices when items are set, never trusted
    from the LLM's own arithmetic (same principle as bot_engine's chat
    pricing guardrail).

    `fulfillment` is schema-free JSONB rather than fixed delivery/pickup
    columns -- this platform spans multiple business types (see the
    design discussion), so its shape is whatever that tenant's flow needs,
    e.g. {"type": "delivery", "address": "...", "needed_by": "2026-12-20"}
    or {"type": "pickup", "time": "..."}.
    """

    __tablename__ = "orders"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status"), default=OrderStatus.DRAFT, nullable=False
    )
    # [{variant_id, product_name, variant_label, quantity, unit_price, line_total}, ...]
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    fulfillment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
