import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.conversations import MessageRole
from app.models.orders import OrderStatus


class OrderUpdate(BaseModel):
    # staff move placed -> completed/cancelled (or cancel a draft) from the
    # dashboard; draft -> placed only ever happens via the bot's
    # confirm_order (repos/orders.py) -- never accepted here
    status: OrderStatus


class OrderRead(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    status: OrderStatus
    items: list[dict]
    total: Decimal
    currency_code: str | None
    fulfillment: dict | None
    notes: str | None
    source_channel: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListItem(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    items: list[dict]
    total: Decimal
    currency_code: str | None
    fulfillment: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderListItem]
    total: int
    page: int
    page_size: int


class TranscriptMessage(BaseModel):
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderDetail(OrderRead):
    # linked lead's captured contact fields, e.g. {"name": ..., "phone": ...}
    # -- empty if this order was never linked to a lead
    lead_fields: dict = {}
    transcript: list[TranscriptMessage] = []
