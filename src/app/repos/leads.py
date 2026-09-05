import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leads import Lead, LeadStatus


async def create_lead_from_bot(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    conversation_id: uuid.UUID | None,
    matched_variant_id: uuid.UUID | None,
    status: LeadStatus,
    fields: dict,
    source_channel: str | None = None,
) -> Lead:
    lead = Lead(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        matched_variant_id=matched_variant_id,
        status=status,
        fields=fields,
        source_channel=source_channel,
    )
    session.add(lead)
    await session.flush()
    return lead
