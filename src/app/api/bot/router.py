import contextlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_service_tenant
from app.db.session import get_db_session
from app.schemas.conversations import BotMessageRequest, BotMessageResponse
from app.services import bot_engine
from app.services.settings_resolver import get_effective_settings

router = APIRouter(prefix="/bot", tags=["bot"])

# LangSmith's distributed-tracing header (see langsmith.run_trees.RunTree.to_headers) --
# only ever present on requests from eval/langsmith_eval/target.py, never from a
# real channel adapter. When present, this nests the LangGraph run below under
# the caller's own trace instead of starting a disconnected root trace (see
# eval/LANGSMITH_PLAN.md section 6). Completely inert otherwise: a request
# without this header hits zero extra code, so real traffic is unaffected.
_TRACE_HEADER = "langsmith-trace"


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

    tracing = contextlib.nullcontext()
    if _TRACE_HEADER in request.headers:
        from langsmith.run_helpers import tracing_context

        tracing = tracing_context(parent=dict(request.headers))

    with tracing:
        return await bot_engine.handle_message(
            session,
            request.app.state.checkpointer,
            tenant_id,
            payload.channel_type,
            payload.external_user_id,
            payload.text,
        )
