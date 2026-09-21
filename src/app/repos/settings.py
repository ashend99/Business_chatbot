"""Tenant-side settings write path (dashboard). The superadmin-only fields
live in repos/settings_admin.py -- keep that split: nothing on the tenant
path may write `TenantAdminSettings`, and the bot (which only ever reads
through services/settings_resolver.py) must not import either write path.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import TenantSettings
from app.repos.settings_read import get_tenant_settings


async def update_tenant_settings(session: AsyncSession, tenant_id: uuid.UUID, **fields: object) -> TenantSettings | None:
    """Only ever called with fields already restricted to tenant-settable
    ones by schemas.settings.TenantSettingsUpdate. Unlike most repo updates,
    an explicit `None` is applied (clearing bot_name, min_order_value, ...)
    -- callers pass only what was actually sent (`exclude_unset`)."""
    row = await get_tenant_settings(session, tenant_id)
    if row is None:
        return None
    for key, value in fields.items():
        setattr(row, key, value)
    await session.flush()
    await session.refresh(row)
    return row
