import uuid

from pydantic import BaseModel

from app.models.conversations import ConversationChannel


class BotMessageAction(BaseModel):
    type: str
    lead_id: uuid.UUID | None = None


class BotMessageRequest(BaseModel):
    channel_type: ConversationChannel
    external_user_id: str
    text: str


class BotMessageResponse(BaseModel):
    reply: str
    conversation_id: uuid.UUID
    actions: list[BotMessageAction] = []
