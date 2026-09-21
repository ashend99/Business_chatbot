import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_service_tenant
from app.db.session import get_db_session
from app.schemas.conversations import BotMessageRequest, BotMessageResponse
from app.services import bot_engine
from app.services.settings_resolver import get_effective_settings

router = APIRouter(prefix="/bot", tags=["bot"])


@router.post("/message", response_model=BotMessageResponse)
async def send_message(
    payload: BotMessageRequest,
    request: Request,
    tenant_id: uuid.UUID = Depends(get_current_service_tenant),
    session: AsyncSession = Depends(get_db_session),
) -> BotMessageResponse:
    # admin-set per-tenant channel allowlist (TenantAdminSettings.allowed_channels)
    effective = await get_effective_settings(tenant_id, session)
    if payload.channel_type.value not in effective.allowed_channels:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"channel {payload.channel_type.value!r} is not enabled for this tenant")

    return await bot_engine.handle_message(
        session,
        request.app.state.checkpointer,
        tenant_id,
        payload.channel_type,
        payload.external_user_id,
        payload.text,
    )
