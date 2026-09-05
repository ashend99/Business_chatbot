import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversations import Conversation, ConversationChannel, Message, MessageRole
from app.repos.tenant_scope import tenant_scope


async def get_or_create_conversation(
    session: AsyncSession, tenant_id: uuid.UUID, channel_type: ConversationChannel, external_user_id: str
) -> Conversation:
    stmt = select(Conversation).where(
        tenant_scope(Conversation.tenant_id, tenant_id),
        Conversation.channel_type == channel_type,
        Conversation.external_user_id == external_user_id,
    )
    conversation = (await session.execute(stmt)).scalar_one_or_none()
    if conversation is not None:
        return conversation

    conversation = Conversation(
        tenant_id=tenant_id,
        channel_type=channel_type,
        external_user_id=external_user_id,
        last_message_at=datetime.now(timezone.utc),
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def get_conversation(session: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation | None:
    stmt = select(Conversation).where(Conversation.id == conversation_id, tenant_scope(Conversation.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def touch_conversation(session: AsyncSession, conversation: Conversation) -> None:
    conversation.last_message_at = datetime.now(timezone.utc)
    await session.flush()


async def add_message(
    session: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID, role: MessageRole, content: str
) -> Message:
    message = Message(tenant_id=tenant_id, conversation_id=conversation_id, role=role, content=content)
    session.add(message)
    await session.flush()
    return message


async def get_recent_messages(
    session: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 10
) -> list[Message]:
    stmt = (
        select(Message)
        .where(tenant_scope(Message.tenant_id, tenant_id), Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = (await session.execute(stmt)).scalars().all()
    return list(reversed(messages))
