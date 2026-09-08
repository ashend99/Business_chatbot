import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant_id
from app.db.session import get_db_session
from app.models.leads import LeadStatus
from app.repos import conversations as conversations_repo
from app.repos import leads_admin as leads_admin_repo
from app.schemas.leads import (
    LeadDetail,
    LeadFieldDefRead,
    LeadFieldDefsReplaceRequest,
    LeadListItem,
    LeadListResponse,
    LeadRead,
    LeadUpdate,
    TranscriptMessage,
)

router = APIRouter(prefix="/tenant", tags=["leads"])


@router.get("/leads", response_model=LeadListResponse)
async def list_leads(
    status_filter: LeadStatus | None = Query(None, alias="status"),
    matched_variant_id: uuid.UUID | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> LeadListResponse:
    items, total = await leads_admin_repo.list_leads(
        session,
        tenant_id,
        status=status_filter,
        matched_variant_id=matched_variant_id,
        search=search,
        page=page,
        page_size=page_size,
    )
    return LeadListResponse(
        items=[LeadListItem.model_validate(lead) for lead in items], total=total, page=page, page_size=page_size
    )


@router.get("/leads/{lead_id}", response_model=LeadDetail)
async def get_lead(
    lead_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> LeadDetail:
    lead = await leads_admin_repo.get_lead(session, tenant_id, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")

    transcript: list[TranscriptMessage] = []
    if lead.conversation_id is not None:
        messages = await conversations_repo.get_recent_messages(session, tenant_id, lead.conversation_id, limit=200)
        transcript = [TranscriptMessage.model_validate(m) for m in messages]

    return LeadDetail(**LeadRead.model_validate(lead).model_dump(), transcript=transcript)


@router.patch("/leads/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> LeadRead:
    lead = await leads_admin_repo.update_lead(session, tenant_id, lead_id, **payload.model_dump(exclude_unset=True))
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")
    await session.commit()
    return LeadRead.model_validate(lead)


@router.get("/lead-field-defs", response_model=list[LeadFieldDefRead])
async def list_lead_field_defs(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[LeadFieldDefRead]:
    defs = await leads_admin_repo.list_lead_field_defs(session, tenant_id)
    return [LeadFieldDefRead.model_validate(d) for d in defs]


@router.put("/lead-field-defs", response_model=list[LeadFieldDefRead])
async def replace_lead_field_defs(
    payload: LeadFieldDefsReplaceRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[LeadFieldDefRead]:
    defs = await leads_admin_repo.replace_lead_field_defs(
        session, tenant_id, [d.model_dump() for d in payload.field_defs]
    )
    await session.commit()
    return [LeadFieldDefRead.model_validate(d) for d in defs]
