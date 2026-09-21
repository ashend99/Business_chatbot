"""Dashboard-facing read/update surface for orders.

Deliberately separate from repos/orders.py, the same way leads_admin.py is
split from leads.py: that module is the bot's only path to DRAFT->PLACED,
and this one must stay import-isolated from it -- the /bot router (and
anything it imports, transitively) must never import from here.
"""

import uuid
from datetime import datetime

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leads import Lead
from app.models.orders import Order, OrderStatus
from app.repos.tenant_scope import tenant_scope


async def list_orders(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: OrderStatus | None = None,
    search: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Order], int]:
    conditions = [tenant_scope(Order.tenant_id, tenant_id)]
    if status is not None:
        conditions.append(Order.status == status)
    if created_after is not None:
        conditions.append(Order.created_at >= created_after)
    if created_before is not None:
        conditions.append(Order.created_at < created_before)
    if search:
        # items is a JSONB list (product names/labels) -- search its whole
        # serialized text rather than a specific key, same approach as
        # leads_admin.list_leads' search over the free-form `fields` JSONB
        conditions.append(cast(Order.items, Text).ilike(f"%{search}%"))

    total_col = func.count().over().label("total")
    stmt = (
        select(Order, total_col)
        .where(*conditions)
        .order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return [], 0
    return [row[0] for row in rows], int(rows[0].total)


async def get_order(session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID) -> Order | None:
    stmt = select(Order).where(Order.id == order_id, tenant_scope(Order.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_lead_fields(session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID | None) -> dict:
    """The linked lead's captured contact fields, for display alongside an
    order's detail (who to actually reach about it) -- reads the Lead model
    directly rather than going through leads_admin.py, since this is a
    read-only lookup by id, not the dashboard's lead list/update surface."""
    if lead_id is None:
        return {}
    stmt = select(Lead.fields).where(Lead.id == lead_id, tenant_scope(Lead.tenant_id, tenant_id))
    fields = (await session.execute(stmt)).scalar_one_or_none()
    return fields or {}


_STAFF_ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.DRAFT: {OrderStatus.CANCELLED},
    # human-confirmation mode: staff accept (-> PLACED) or reject (-> CANCELLED)
    OrderStatus.PENDING_CONFIRMATION: {OrderStatus.PLACED, OrderStatus.CANCELLED},
    OrderStatus.PLACED: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
}


async def update_order_status(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID, status: OrderStatus
) -> tuple[Order | None, bool]:
    """Returns (order, ok). ok is False when the order exists but the
    requested transition isn't one staff may make by hand -- DRAFT/PLACED
    are bot-owned states the dashboard can only move *out of* (to
    CANCELLED, or PLACED to COMPLETED), never back into or between."""
    order = await get_order(session, tenant_id, order_id)
    if order is None:
        return None, False
    if status not in _STAFF_ALLOWED_TRANSITIONS.get(order.status, set()):
        return order, False

    order.status = status
    await session.flush()
    await session.refresh(order)
    return order, True
