"""Dashboard-facing read/update surface for leads (Phase 5).

Deliberately a separate file from repos/leads.py: that module is the bot's
only write path and must stay import-isolated from this one -- the /bot
router (and anything it imports, transitively) must never import from
leads_admin. Splitting into two files makes that boundary structurally
obvious rather than just a comment.
"""

import uuid
from datetime import datetime

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leads import Lead, LeadFieldDef, LeadFieldType, LeadStatus
from app.repos.tenant_scope import tenant_scope

# ---- leads (read/update only -- creation is bot-only, see repos/leads.py) --


async def list_leads(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: LeadStatus | None = None,
    matched_variant_id: uuid.UUID | None = None,
    search: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Lead], int]:
    conditions = [tenant_scope(Lead.tenant_id, tenant_id)]
    if status is not None:
        conditions.append(Lead.status == status)
    if matched_variant_id is not None:
        conditions.append(Lead.matched_variant_id == matched_variant_id)
    if created_after is not None:
        conditions.append(Lead.created_at >= created_after)
    if created_before is not None:
        conditions.append(Lead.created_at < created_before)
    if search:
        # fields is free-form JSONB (dynamic per-tenant schema) -- search
        # across its whole serialized text rather than a specific key, so
        # a search box works regardless of which fields a tenant configured
        conditions.append(cast(Lead.fields, Text).ilike(f"%{search}%"))

    # count(*) OVER() gives the full filtered total in the same round trip as
    # the page of rows -- one query to the (remote) DB instead of two. When
    # the requested page is past the end there are no rows and total reads 0;
    # the dashboard's pager never requests such a page.
    total_col = func.count().over().label("total")
    stmt = (
        select(Lead, total_col)
        .where(*conditions)
        .order_by(Lead.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return [], 0
    return [row[0] for row in rows], int(rows[0].total)


async def get_lead(session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID) -> Lead | None:
    stmt = select(Lead).where(Lead.id == lead_id, tenant_scope(Lead.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_lead(session: AsyncSession, tenant_id: uuid.UUID, lead_id: uuid.UUID, **fields: object) -> Lead | None:
    """status/notes/deal_value only -- enforced by the schema layer
    (schemas.leads.LeadUpdate), not here; this just applies whatever
    fields it's given."""
    lead = await get_lead(session, tenant_id, lead_id)
    if lead is None:
        return None
    for key, value in fields.items():
        if value is not None:
            setattr(lead, key, value)
    await session.flush()
    # updated_at is a server-side onupdate default -- refresh so the ORM
    # object reflects the new value instead of lazily reloading it later
    # outside an async-aware context (which raises MissingGreenlet).
    await session.refresh(lead)
    return lead


# ---- lead field definitions (the dynamic per-tenant schema) ---------------


DEFAULT_LEAD_FIELD_DEFS: list[dict] = [
    {"field_key": "name", "label": "Name", "field_type": LeadFieldType.TEXT, "required": True, "sort_order": 1},
    {"field_key": "phone", "label": "Phone Number", "field_type": LeadFieldType.PHONE, "required": True, "sort_order": 2},
    {"field_key": "email", "label": "Email", "field_type": LeadFieldType.EMAIL, "required": False, "sort_order": 3},
]


async def list_lead_field_defs(session: AsyncSession, tenant_id: uuid.UUID) -> list[LeadFieldDef]:
    stmt = (
        select(LeadFieldDef)
        .where(tenant_scope(LeadFieldDef.tenant_id, tenant_id))
        .order_by(LeadFieldDef.sort_order, LeadFieldDef.field_key)
    )
    return list((await session.execute(stmt)).scalars().all())


async def seed_default_lead_field_defs(session: AsyncSession, tenant_id: uuid.UUID) -> list[LeadFieldDef]:
    """Sensible defaults (name/phone/email) for a freshly onboarded tenant
    -- called from services/onboarding.py's onboard_tenant. Clients
    edit/add/remove from there via replace_lead_field_defs."""
    rows = [
        LeadFieldDef(
            tenant_id=tenant_id,
            field_key=d["field_key"],
            label=d["label"],
            field_type=d["field_type"],
            required=d["required"],
            sort_order=d["sort_order"],
        )
        for d in DEFAULT_LEAD_FIELD_DEFS
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def replace_lead_field_defs(session: AsyncSession, tenant_id: uuid.UUID, defs: list[dict]) -> list[LeadFieldDef]:
    """Full replace (PUT semantics): delete this tenant's existing field
    defs, insert the new set. Simpler and safer than trying to diff/merge
    -- a tenant's lead-capture schema is small and edited rarely."""
    existing = await list_lead_field_defs(session, tenant_id)
    for row in existing:
        await session.delete(row)
    await session.flush()

    rows = [
        LeadFieldDef(
            tenant_id=tenant_id,
            field_key=d["field_key"],
            label=d["label"],
            field_type=d["field_type"],
            required=d.get("required", False),
            sort_order=d.get("sort_order", i),
        )
        for i, d in enumerate(defs)
    ]
    session.add_all(rows)
    await session.flush()
    return rows
