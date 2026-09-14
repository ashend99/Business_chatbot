"""Bot-only write path for orders (cart-building + confirm, minus payment).

Mirrors repos/leads.py's shape and constraints: this is the only entry point
the bot agent (services/bot_tools.py) may use to write orders. There is no
dashboard-facing read/update surface yet -- the future Orders page gets its
own repo module the same way leads_admin.py is separate from leads.py.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Product, Variant
from app.models.leads import Lead
from app.models.orders import Order, OrderStatus
from app.repos import leads as leads_repo
from app.repos.tenant_scope import tenant_scope


class InvalidOrderItem(ValueError):
    """Raised when update_order is asked to add a variant_id that doesn't
    exist, isn't active, or doesn't belong to this tenant -- lets the tool
    layer turn this into a message the agent can recover from conversationally,
    rather than the whole turn failing with an unhandled exception."""


class NoCartToConfirm(ValueError):
    """Raised by confirm_order when there is no draft order (or it has no
    items) for this conversation yet."""


class MissingRequiredContactInfo(ValueError):
    """Raised by confirm_order when this tenant's dashboard-configured
    required lead fields (see leads_repo.get_missing_required_fields)
    aren't all filled in yet -- an order can't be handed to a human to
    fulfill/collect payment on if there's no way to reach the customer."""

    def __init__(self, missing_labels: list[str]) -> None:
        self.missing_labels = missing_labels
        super().__init__(f"missing required contact info: {', '.join(missing_labels)}")


async def _price_items(
    session: AsyncSession, tenant_id: uuid.UUID, items: list[dict]
) -> tuple[list[dict], Decimal]:
    """Turns [{"variant_id": ..., "quantity": ...}, ...] into priced line
    items using *real* catalog data (product name, variant label, current
    price) -- never trusting a price or name the LLM might supply, the same
    principle as bot_engine's chat pricing guardrail."""
    priced: list[dict] = []
    total = Decimal("0")
    for raw in items:
        variant_id = uuid.UUID(str(raw["variant_id"]))
        quantity = int(raw["quantity"])
        if quantity < 1:
            raise InvalidOrderItem(f"quantity must be at least 1 (got {quantity})")

        stmt = (
            select(Variant, Product)
            .join(Product, Product.id == Variant.product_id)
            .where(
                tenant_scope(Variant.tenant_id, tenant_id),
                Variant.id == variant_id,
                Variant.active.is_(True),
            )
        )
        row = (await session.execute(stmt)).first()
        if row is None:
            raise InvalidOrderItem(f"no active catalog item found for variant_id {variant_id}")
        variant, product = row

        unit_price = variant.price
        line_total = unit_price * quantity
        total += line_total
        priced.append(
            {
                "variant_id": str(variant.id),
                "product_name": product.name,
                "variant_label": variant.name,
                "quantity": quantity,
                "unit_price": str(unit_price),
                "line_total": str(line_total),
            }
        )
    return priced, total


async def _get_draft_order(session: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> Order | None:
    stmt = select(Order).where(
        tenant_scope(Order.tenant_id, tenant_id),
        Order.conversation_id == conversation_id,
        Order.status == OrderStatus.DRAFT,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _linked_lead_id(session: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> uuid.UUID | None:
    """A Lead may be created before, after, or never relative to the cart
    being built -- this re-checks on every order write so `Order.lead_id`
    self-heals into place whichever order the two tools get called in,
    rather than the agent having to manage the link itself."""
    stmt = select(Lead.id).where(tenant_scope(Lead.tenant_id, tenant_id), Lead.conversation_id == conversation_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    conversation_id: uuid.UUID,
    items: list[dict],
    fulfillment: dict | None = None,
    notes: str | None = None,
    source_channel: str | None = None,
) -> Order:
    """Upsert-by-conversation, full-replace semantics: the agent sends the
    *entire* current cart each call (matching create_lead's fields-dict
    pattern) rather than incremental add/remove deltas -- simpler for an
    LLM to reason about, since it just states what the cart should be now.

    Only ever touches a DRAFT order for this conversation. Once an order
    has been confirmed (PLACED) or later completed/cancelled, a further
    update_order call starts a *new* draft rather than mutating history --
    a placed order is a frozen record of what was agreed.
    """
    # Same race as leads: LangGraph may run multiple tool calls from one
    # turn concurrently, each in its own session -- serialize per
    # conversation so two update_order calls (or an update_order racing a
    # create_lead) can't both miss the same not-yet-committed row. Reusing
    # leads.py's exact lock key is intentional: it also protects against an
    # update_order racing a create_lead's lead_id-linking read below.
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(conversation_id)))))

    priced_items, total = await _price_items(session, tenant_id, items)
    lead_id = await _linked_lead_id(session, tenant_id, conversation_id)

    order = await _get_draft_order(session, tenant_id, conversation_id)
    if order is None:
        order = Order(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            lead_id=lead_id,
            status=OrderStatus.DRAFT,
            items=priced_items,
            total=total,
            fulfillment=fulfillment,
            notes=notes,
            source_channel=source_channel,
        )
        session.add(order)
        await session.flush()
        return order

    order.items = priced_items
    order.total = total
    if lead_id is not None:
        order.lead_id = lead_id
    if fulfillment is not None:
        order.fulfillment = fulfillment
    if notes is not None:
        order.notes = notes
    if source_channel is not None:
        order.source_channel = source_channel
    await session.flush()
    await session.refresh(order)
    return order


async def confirm_order(session: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> Order:
    """Moves this conversation's draft order from DRAFT to PLACED -- the
    handoff point to a human for payment/fulfillment. Raises NoCartToConfirm
    or MissingRequiredContactInfo instead of returning None so the tool
    layer can tell the agent exactly what's missing (an empty cart vs. no
    way to reach the customer), rather than a bare failure."""
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(conversation_id)))))

    order = await _get_draft_order(session, tenant_id, conversation_id)
    if order is None or not order.items:
        raise NoCartToConfirm()

    lead_id = await _linked_lead_id(session, tenant_id, conversation_id)
    if lead_id is not None:
        order.lead_id = lead_id

    missing_fields = await leads_repo.get_missing_required_fields(session, tenant_id, lead_id)
    if missing_fields:
        raise MissingRequiredContactInfo(missing_fields)

    order.status = OrderStatus.PLACED
    await session.flush()
    await session.refresh(order)
    return order
