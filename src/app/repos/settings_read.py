"""Read-only settings queries -- the only settings repo the bot's resolver
(services/settings_resolver.py) imports, so the bot path never has a write
function in reach. Writes: repos/settings.py (tenant), repos/settings_admin.py
(superadmin).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import TenantAdminSettings, TenantSettings
from app.repos.tenant_scope import tenant_scope


async def get_tenant_settings(session: AsyncSession, tenant_id: uuid.UUID) -> TenantSettings | None:
    stmt = select(TenantSettings).where(tenant_scope(TenantSettings.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_admin_settings(session: AsyncSession, tenant_id: uuid.UUID) -> TenantAdminSettings | None:
    stmt = select(TenantAdminSettings).where(tenant_scope(TenantAdminSettings.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()
