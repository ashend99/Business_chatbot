"""Dashboard-facing read models for the Conversations page -- distinct from
schemas/conversations.py, which is the bot's own request/response contract.
This surface is read-only: the dashboard never writes messages or changes a
conversation's status (that's the bot's job)."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.conversations import ConversationChannel, ConversationStatus, MessageRole


class ConversationListItem(BaseModel):
    id: uuid.UUID
    channel_type: ConversationChannel
    external_user_id: str
    status: ConversationStatus
    last_message_at: datetime
    last_message_preview: str | None = None

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    items: list[ConversationListItem]
    total: int
    page: int
    page_size: int


class MessageRead(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetail(BaseModel):
    id: uuid.UUID
    channel_type: ConversationChannel
    external_user_id: str
    status: ConversationStatus
    last_message_at: datetime
    messages: list[MessageRead]

    model_config = {"from_attributes": True}
