import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant_id
from app.db.session import get_db_session
from app.models.orders import OrderStatus
from app.repos import conversations as conversations_repo
from app.repos import orders_admin as orders_admin_repo
from app.schemas.orders import OrderDetail, OrderListItem, OrderListResponse, OrderRead, OrderUpdate, TranscriptMessage

router = APIRouter(prefix="/tenant/orders", tags=["orders"])


@router.get("", response_model=OrderListResponse)
async def list_orders(
    status_filter: OrderStatus | None = Query(None, alias="status"),
    search: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> OrderListResponse:
    items, total = await orders_admin_repo.list_orders(
        session,
        tenant_id,
        status=status_filter,
        search=search,
        created_after=created_after,
        created_before=created_before,
        page=page,
        page_size=page_size,
    )
    return OrderListResponse(
        items=[OrderListItem.model_validate(o) for o in items], total=total, page=page, page_size=page_size
    )


@router.get("/{order_id}", response_model=OrderDetail)
async def get_order(
    order_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> OrderDetail:
    order = await orders_admin_repo.get_order(session, tenant_id, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")

    lead_fields = await orders_admin_repo.get_lead_fields(session, tenant_id, order.lead_id)

    transcript: list[TranscriptMessage] = []
    if order.conversation_id is not None:
        messages = await conversations_repo.get_recent_messages(session, tenant_id, order.conversation_id, limit=200)
        transcript = [TranscriptMessage.model_validate(m) for m in messages]

    return OrderDetail(**OrderRead.model_validate(order).model_dump(), lead_fields=lead_fields, transcript=transcript)


@router.patch("/{order_id}", response_model=OrderRead)
async def update_order(
    order_id: uuid.UUID,
    payload: OrderUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> OrderRead:
    order, ok = await orders_admin_repo.update_order_status(session, tenant_id, order_id, payload.status)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"cannot move an order from {order.status.value} to {payload.status.value}")
    await session.commit()
    return OrderRead.model_validate(order)
