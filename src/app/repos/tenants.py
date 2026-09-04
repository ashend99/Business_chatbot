import uuid
from datetime import datetime, timedelta, timezone
import logging


from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_raw_token, hash_token
from app.models import InviteTokens, Tenant, TenantAdmin
from common import PROJECT_CONFIG

logger = logging.getLogger(__name__)

async def get_tenant_by_id(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    return await session.get(Tenant, tenant_id)


async def list_tenants(
    session: AsyncSession,
    *,
    is_active: bool | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Tenant], int]:
    stmt = select(Tenant)
    count_stmt = select(func.count()).select_from(Tenant)
    if is_active is not None:
        stmt = stmt.where(Tenant.is_active == is_active)
        count_stmt = count_stmt.where(Tenant.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Tenant.name.ilike(pattern))
        count_stmt = count_stmt.where(Tenant.name.ilike(pattern))

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Tenant.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await session.execute(stmt)).scalars().all()
    return list(items), total


async def update_tenant(session: AsyncSession, tenant_id: uuid.UUID, **fields: object) -> Tenant | None:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        return None
    for key, value in fields.items():
        if value is not None:
            setattr(tenant, key, value)
    await session.flush()
    return tenant


async def set_tenant_active(session: AsyncSession, tenant_id: uuid.UUID, is_active: bool) -> Tenant | None:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        return None
    tenant.is_active = is_active
    await session.flush()
    return tenant


async def invalidate_pending_invites(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    stmt = select(InviteTokens).where(InviteTokens.tenant_id == tenant_id, InviteTokens.is_used.is_(False))
    invites = (await session.execute(stmt)).scalars().all()
    for invite in invites:
        invite.is_used = True
    await session.flush()


async def create_tenant(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    email: str | None = None,
    contact_person: str | None = None,
    contact_number: str | None = None,
    address: str | None = None,
) -> Tenant:
    tenant = Tenant(
        name=name,
        slug=slug,
        email=email,
        contact_person=contact_person,
        contact_number=contact_number,
        address=address,
    )
    session.add(tenant)
    await session.flush()
    return tenant


async def get_tenant_admin_by_username(session: AsyncSession, username: str) -> TenantAdmin | None:
    stmt = select(TenantAdmin).where(TenantAdmin.username == username)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_tenant_admin_by_tenant_id(session: AsyncSession, tenant_id: uuid.UUID) -> TenantAdmin | None:
    return await session.get(TenantAdmin, tenant_id)


async def create_tenant_admin(
    session: AsyncSession, *, tenant_id: uuid.UUID, username: str, hashed_password: str
) -> TenantAdmin:
    admin = TenantAdmin(tenant_id=tenant_id, username=username, hashed_password=hashed_password)
    session.add(admin)
    await session.flush()
    return admin


async def update_tenant_admin_password(session: AsyncSession, admin: TenantAdmin, hashed_password: str) -> None:
    admin.hashed_password = hashed_password
    await session.flush()


async def create_invite_token(
    session: AsyncSession, *, tenant_id: uuid.UUID, expires_in_hours: int = 72
) -> tuple[InviteTokens, str]:
    raw_token = generate_raw_token()
    logger.info(f"Generated raw invite token: {raw_token}")
    expires_in_mins = PROJECT_CONFIG.get("auth").get("tenant").get("activation_token_expire_minutes", 60)
    invite = InviteTokens(
        tenant_id=tenant_id,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=expires_in_mins),
    )
    session.add(invite)
    await session.flush()
    return invite, raw_token


async def get_invite_token_by_hash(session: AsyncSession, token_hash: str) -> InviteTokens | None:
    stmt = select(InviteTokens).where(InviteTokens.token_hash == token_hash)
    return (await session.execute(stmt)).scalar_one_or_none()


async def mark_invite_used(session: AsyncSession, invite: InviteTokens) -> None:
    invite.is_used = True
    invite.used_at = datetime.now(timezone.utc)
    await session.flush()


def is_invite_valid(invite: InviteTokens) -> bool:
    return not invite.is_used and invite.expires_at > datetime.now(timezone.utc)
