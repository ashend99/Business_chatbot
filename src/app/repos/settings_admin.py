"""Superadmin-only settings surface: create the per-tenant rows at
onboarding and edit the admin fields afterwards. Deliberately separate from
repos/settings.py -- tenants must never reach `TenantAdminSettings` writes.
Not tenant-scoped (the superadmin manages any tenant, active or suspended).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import TenantAdminSettings, TenantSettings


async def create_default_settings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    currency_code: str = "USD",
    timezone: str = "UTC",
    **admin_fields: object,
) -> tuple[TenantAdminSettings, TenantSettings]:
    """Both rows for a freshly onboarded tenant. `timezone` is the tenant's
    to change later; everything in `admin_fields`/`currency_code` is not."""
    admin = TenantAdminSettings(tenant_id=tenant_id, currency_code=currency_code.upper(), **admin_fields)
    tenant = TenantSettings(tenant_id=tenant_id, timezone=timezone)
    session.add_all([admin, tenant])
    await session.flush()
    return admin, tenant


async def get_admin_settings(session: AsyncSession, tenant_id: uuid.UUID) -> TenantAdminSettings | None:
    return (
        await session.execute(select(TenantAdminSettings).where(TenantAdminSettings.tenant_id == tenant_id))
    ).scalar_one_or_none()


async def update_admin_settings(
    session: AsyncSession, tenant_id: uuid.UUID, **fields: object
) -> TenantAdminSettings | None:
    row = await get_admin_settings(session, tenant_id)
    if row is None:
        return None
    for key, value in fields.items():
        setattr(row, key, value.upper() if key == "currency_code" and isinstance(value, str) else value)
    await session.flush()
    await session.refresh(row)
    return row
