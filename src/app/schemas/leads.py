import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.conversations import MessageRole
from app.models.leads import LeadFieldType, LeadStatus


class LeadFieldDefCreate(BaseModel):
    field_key: str
    label: str
    field_type: LeadFieldType = LeadFieldType.TEXT
    required: bool = False
    sort_order: int = 0


class LeadFieldDefRead(BaseModel):
    id: uuid.UUID
    field_key: str
    label: str
    field_type: LeadFieldType
    required: bool
    sort_order: int

    model_config = {"from_attributes": True}


class LeadFieldDefsReplaceRequest(BaseModel):
    field_defs: list[LeadFieldDefCreate]


class LeadUpdate(BaseModel):
    # never field_values/fields -- those are bot-write-only (see
    # repos/leads.py); the dashboard may only change these three
    status: LeadStatus | None = None
    notes: str | None = None
    deal_value: Decimal | None = None


class LeadRead(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    matched_variant_id: uuid.UUID | None
    status: LeadStatus
    fields: dict
    source_channel: str | None
    deal_value: Decimal | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LeadListItem(BaseModel):
    id: uuid.UUID
    status: LeadStatus
    fields: dict
    matched_variant_id: uuid.UUID | None
    deal_value: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadListResponse(BaseModel):
    items: list[LeadListItem]
    total: int
    page: int
    page_size: int


class TranscriptMessage(BaseModel):
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadDetail(LeadRead):
    # full conversation transcript, oldest first -- empty if the lead has
    # no linked conversation (conversation_id is nullable)
    transcript: list[TranscriptMessage] = []
