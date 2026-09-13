import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant_id
from app.db.session import get_db_session
from app.models.conversations import ConversationChannel, ConversationStatus
from app.repos import conversations as conversations_repo
from app.schemas.conversations_admin import ConversationDetail, ConversationListItem, ConversationListResponse

router = APIRouter(prefix="/tenant/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    channel: ConversationChannel | None = Query(None, alias="channel"),
    status_filter: ConversationStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationListResponse:
    rows, total = await conversations_repo.list_conversations(
        session, tenant_id, channel_type=channel, status=status_filter, page=page, page_size=page_size
    )
    items = [
        ConversationListItem(
            id=conversation.id,
            channel_type=conversation.channel_type,
            external_user_id=conversation.external_user_id,
            status=conversation.status,
            last_message_at=conversation.last_message_at,
            last_message_preview=preview,
        )
        for conversation, preview in rows
    ]
    return ConversationListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationDetail:
    conversation = await conversations_repo.get_conversation(session, tenant_id, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    messages = await conversations_repo.get_recent_messages(session, tenant_id, conversation_id, limit=500)
    return ConversationDetail(
        id=conversation.id,
        channel_type=conversation.channel_type,
        external_user_id=conversation.external_user_id,
        status=conversation.status,
        last_message_at=conversation.last_message_at,
        messages=messages,
    )
