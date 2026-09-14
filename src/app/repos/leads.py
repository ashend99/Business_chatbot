"""Bot-only write path for leads (Phase 5).

This is the single entry point the bot agent (services/bot_tools.py) may
use -- no read/list/update capability over *existing* leads lives here
beyond the upsert lookup below. See repos/leads_admin.py for the separate
dashboard-facing read/update surface; the /bot router (and anything it
imports) must never reach into that module.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leads import Lead, LeadFieldDef, LeadStatus
from app.models.orders import Order
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
        # LangGraph's ToolNode runs multiple tool calls from one LLM turn
        # concurrently via asyncio.gather (see bot_tools.py's build_tools
        # docstring), and each tool call opens its own session/transaction
        # -- so two create_lead calls in the same turn (e.g. one
        # "interested", one "new" once details come in) can otherwise both
        # find no existing row and both INSERT, producing duplicate leads
        # for one conversation. A transaction-scoped advisory lock keyed on
        # conversation_id serializes them: the second call blocks here
        # until the first commits (releasing the lock), so its SELECT below
        # then correctly sees the just-inserted row and takes the UPDATE
        # branch instead.
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(str(conversation_id)))))
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
        became_new = status == LeadStatus.NEW
    else:
        lead = existing
        became_new = status == LeadStatus.NEW and existing.status != LeadStatus.NEW
        lead.status = status
        lead.fields = {**lead.fields, **fields}
        if matched_variant_id is not None:
            lead.matched_variant_id = matched_variant_id
        if source_channel is not None:
            lead.source_channel = source_channel
        await session.flush()
        # updated_at is a server-side onupdate default -- refresh so the
        # ORM object reflects the new value instead of lazily reloading it
        # later outside an async-aware context (which raises MissingGreenlet).
        await session.refresh(lead)

    if conversation_id is not None:
        # repos/orders.py links Order.lead_id -> this lead the same way,
        # the moment it sees one exist -- but if create_lead and
        # update_order/confirm_order both fire in the same LLM turn, they
        # run concurrently (see the docstring above) and whichever commits
        # first won't see the other's not-yet-committed row. Re-checking
        # here too means the link self-heals from whichever side runs
        # last, instead of only ever getting attached from the order side.
        order_stmt = select(Order).where(
            tenant_scope(Order.tenant_id, tenant_id), Order.conversation_id == conversation_id, Order.lead_id.is_(None)
        )
        for order in (await session.execute(order_stmt)).scalars().all():
            order.lead_id = lead.id
        await session.flush()

    return lead, became_new


async def get_missing_required_fields(
    session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID | None
) -> list[str]:
    """Labels of this tenant's dashboard-configured required lead fields
    (LeadFieldDef.required, seeded name/phone by default -- see
    leads_admin.seed_default_lead_field_defs) that aren't yet filled in on
    the given lead. Used by repos/orders.py's confirm_order to require real
    contact info before an order can be placed, without hardcoding "name"/
    "phone" -- whatever a tenant has actually marked required is what's
    enforced, so this generalizes across each tenant's own configured
    fields rather than assuming every business wants the same two."""
    stmt = (
        select(LeadFieldDef.field_key, LeadFieldDef.label)
        .where(tenant_scope(LeadFieldDef.tenant_id, tenant_id), LeadFieldDef.required.is_(True))
        .order_by(LeadFieldDef.sort_order)
    )
    required = (await session.execute(stmt)).all()
    if not required:
        return []

    lead_fields: dict = {}
    if lead_id is not None:
        lead = await session.get(Lead, lead_id)
        if lead is not None:
            lead_fields = lead.fields or {}

    return [label for field_key, label in required if not lead_fields.get(field_key)]
