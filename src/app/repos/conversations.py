import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversations import Conversation, ConversationChannel, ConversationStatus, Message, MessageRole
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
    # created_at is set explicitly here (rather than left to the column's
    # server_default=func.now()) because a turn's user + assistant messages
    # are typically flushed within the same transaction, and Postgres's
    # now() returns the transaction's start time for every statement in it
    # -- both rows would get an identical timestamp, making transcript order
    # (get_recent_messages/list_conversations' preview) non-deterministic.
    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=datetime.now(timezone.utc),
    )
    session.add(message)
    await session.flush()
    return message


async def list_conversations(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    channel_type: ConversationChannel | None = None,
    status: ConversationStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[Conversation, str | None]], int]:
    """Returns (conversation, last_message_preview) pairs, newest first --
    the preview is a correlated-subquery lookup of that conversation's most
    recent message content, so the list view doesn't need a second N+1
    round-trip per row."""
    preview = (
        select(Message.content)
        .where(Message.conversation_id == Conversation.id)
        .order_by(Message.created_at.desc())
        .limit(1)
        .correlate(Conversation)
        .scalar_subquery()
    )
    stmt = select(Conversation, preview).where(tenant_scope(Conversation.tenant_id, tenant_id))
    count_stmt = select(func.count()).select_from(Conversation).where(tenant_scope(Conversation.tenant_id, tenant_id))
    if channel_type is not None:
        stmt = stmt.where(Conversation.channel_type == channel_type)
        count_stmt = count_stmt.where(Conversation.channel_type == channel_type)
    if status is not None:
        stmt = stmt.where(Conversation.status == status)
        count_stmt = count_stmt.where(Conversation.status == status)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Conversation.last_message_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1]) for row in rows], total


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
