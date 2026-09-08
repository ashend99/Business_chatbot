"""Bot-only write path for leads (Phase 5).

This is the single entry point the bot agent (services/bot_tools.py) may
use -- no read/list/update capability over *existing* leads lives here
beyond the upsert lookup below. See repos/leads_admin.py for the separate
dashboard-facing read/update surface; the /bot router (and anything it
imports) must never reach into that module.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leads import Lead, LeadStatus
from app.repos.tenant_scope import tenant_scope


async def create_or_update_lead_from_bot(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    conversation_id: uuid.UUID | None,
    matched_variant_id: uuid.UUID | None,
    status: LeadStatus,
    fields: dict,
    source_channel: str | None = None,
) -> tuple[Lead, bool]:
    """Upsert by (tenant_id, conversation_id): one conversation produces at
    most one lead row, refined over multiple turns (e.g. INTERESTED as
    soon as intent is clear, then updated to NEW once contact details come
    in) rather than a new duplicate row per tool call.

    Returns (lead, became_new) -- became_new is True only for the specific
    transition into status=NEW (a fresh insert as NEW, or an update from a
    different status to NEW), so the caller can decide whether to send a
    new-lead notification exactly once, not on every subsequent call.
    """
    existing: Lead | None = None
    if conversation_id is not None:
        stmt = select(Lead).where(tenant_scope(Lead.tenant_id, tenant_id), Lead.conversation_id == conversation_id)
        existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing is None:
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
        return lead, status == LeadStatus.NEW

    became_new = status == LeadStatus.NEW and existing.status != LeadStatus.NEW
    existing.status = status
    existing.fields = {**existing.fields, **fields}
    if matched_variant_id is not None:
        existing.matched_variant_id = matched_variant_id
    if source_channel is not None:
        existing.source_channel = source_channel
    await session.flush()
    # updated_at is a server-side onupdate default -- refresh so the ORM
    # object reflects the new value instead of lazily reloading it later
    # outside an async-aware context (which raises MissingGreenlet).
    await session.refresh(existing)
    return existing, became_new
