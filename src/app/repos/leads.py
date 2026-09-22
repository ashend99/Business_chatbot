"""Bot-only write path for leads (Phase 5).

This is the single entry point the bot agent (services/bot_tools.py) may
use -- no read/list/update capability over *existing* leads lives here
beyond the upsert lookup below. See repos/leads_admin.py for the separate
dashboard-facing read/update surface; the /bot router (and anything it
imports) must never reach into that module.
"""

import uuid
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leads import Lead, LeadFieldDef, LeadStatus
from app.models.orders import Order
from app.repos.tenant_scope import tenant_scope

# Statuses staff set from the dashboard. Once a lead is in one of these the
# bot must never move it -- otherwise a customer who keeps chatting after
# being contacted would silently reset the lead back to NEW/INTERESTED.
_STAFF_OWNED_STATUSES = frozenset({LeadStatus.CONTACTED, LeadStatus.CONVERTED, LeadStatus.LOST})


class LeadUpsertResult(NamedTuple):
    lead: Lead
    # True only for the specific transition into status=NEW, so the caller
    # can send the new-lead notification exactly once
    became_new: bool
    # Labels of required fields still missing when the bot asked for NEW; if
    # non-empty the lead was kept at INTERESTED instead (or, for a lead
    # that's already NEW, left as it was) and the agent should be told what
    # to collect
    missing_required: list[str]


def resolve_bot_status(existing: LeadStatus | None, requested: LeadStatus, missing_required: list[str]) -> LeadStatus:
    """The status a lead ends up with when the bot asks for `requested`."""
    if existing is not None and existing in _STAFF_OWNED_STATUSES:
        return existing  # staff own it now: hands off
    if existing == LeadStatus.NEW:
        return LeadStatus.NEW  # the bot never downgrades NEW back to INTERESTED
    # a fresh lead or an INTERESTED one: NEW only with the required details
    if requested == LeadStatus.NEW and missing_required:
        return LeadStatus.INTERESTED
    return requested


async def create_or_update_lead_from_bot(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    conversation_id: uuid.UUID | None,
    matched_variant_id: uuid.UUID | None,
    status: LeadStatus,
    fields: dict,
    source_channel: str | None = None,
) -> LeadUpsertResult:
    """Upsert by (tenant_id, conversation_id): one conversation produces at
    most one lead row, refined over multiple turns (e.g. INTERESTED as
    soon as intent is clear, then updated to NEW once contact details come
    in) rather than a new duplicate row per tool call.

    Status is enforced here, not left to the agent:
    - the bot only ever moves a lead forward (INTERESTED -> NEW), never back;
    - a lead staff have moved to CONTACTED/CONVERTED/LOST keeps its status
      (new field values are still merged in);
    - NEW requires every field the tenant marked required (LeadFieldDef) to
      be filled, counting values already on the lead -- otherwise the lead
      stays INTERESTED and `missing_required` says what's missing.

    See LeadUpsertResult for what's returned.
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

    # what the lead's fields will be after this call -- NEW is judged on this
    merged_fields = {**(existing.fields if existing is not None else {}), **fields}
    missing_required: list[str] = []
    if status == LeadStatus.NEW:
        missing_required = await _missing_required_labels(session, tenant_id, merged_fields)

    new_status = resolve_bot_status(existing.status if existing is not None else None, status, missing_required)

    if existing is None:
        lead = Lead(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            matched_variant_id=matched_variant_id,
            status=new_status,
            fields=fields,
            source_channel=source_channel,
        )
        session.add(lead)
        await session.flush()
        became_new = new_status == LeadStatus.NEW
    else:
        lead = existing
        became_new = new_status == LeadStatus.NEW and existing.status != LeadStatus.NEW
        lead.status = new_status
        lead.fields = merged_fields
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

    return LeadUpsertResult(lead, became_new, missing_required)


async def _missing_required_labels(session: AsyncSession, tenant_id: uuid.UUID, lead_fields: dict) -> list[str]:
    """Labels of this tenant's required LeadFieldDefs that have no value in
    `lead_fields`."""
    stmt = (
        select(LeadFieldDef.field_key, LeadFieldDef.label)
        .where(tenant_scope(LeadFieldDef.tenant_id, tenant_id), LeadFieldDef.required.is_(True))
        .order_by(LeadFieldDef.sort_order)
    )
    required = (await session.execute(stmt)).all()
    return [label for field_key, label in required if not lead_fields.get(field_key)]


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
    lead_fields: dict = {}
    if lead_id is not None:
        lead = await session.get(Lead, lead_id)
        if lead is not None:
            lead_fields = lead.fields or {}

    return await _missing_required_labels(session, tenant_id, lead_fields)
