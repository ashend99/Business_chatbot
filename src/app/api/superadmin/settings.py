"""Superadmin-only: a tenant's admin-set settings and its api_secret keys.
Tenants can read a trimmed view of the former (GET /tenant/settings) and
have no access to either the admin fields' write path or key management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_platform_admin
from app.db.session import get_db_session
from app.models.tenants import ApiKeyTypes
from app.repos import settings_admin as settings_admin_repo
from app.repos import tenants as tenants_repo
from app.schemas.settings import AdminSettingsRead, AdminSettingsUpdate, ApiKeyCreated, ApiKeyRead
from app.services import settings_resolver

router = APIRouter(
    prefix="/superadmin/tenants/{tenant_id}",
    tags=["superadmin"],
    dependencies=[Depends(get_current_platform_admin)],
)

# columns that are nullable -- an explicit `null` clears them; for every
# other field null is a 422 rather than a DB IntegrityError
_NULLABLE = {"llm_model", "monthly_message_limit", "max_documents"}


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    if await tenants_repo.get_tenant_by_id(session, tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")


@router.get("/settings", response_model=AdminSettingsRead)
async def get_admin_settings(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)) -> AdminSettingsRead:
    await _require_tenant(session, tenant_id)
    row = await settings_admin_repo.get_admin_settings(session, tenant_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "settings not found for this tenant")
    return AdminSettingsRead.model_validate(row)


@router.patch("/settings", response_model=AdminSettingsRead)
async def update_admin_settings(
    tenant_id: uuid.UUID, payload: AdminSettingsUpdate, session: AsyncSession = Depends(get_db_session)
) -> AdminSettingsRead:
    await _require_tenant(session, tenant_id)
    fields = payload.model_dump(exclude_unset=True)
    nulled = [k for k, v in fields.items() if v is None and k not in _NULLABLE]
    if nulled:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"cannot set to null: {sorted(nulled)}")

    row = await settings_admin_repo.update_admin_settings(session, tenant_id, **fields)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "settings not found for this tenant")
    await session.commit()
    settings_resolver.invalidate(tenant_id)
    return AdminSettingsRead.model_validate(row)


@router.get("/api-keys", response_model=list[ApiKeyRead])
async def list_api_keys(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)) -> list[ApiKeyRead]:
    await _require_tenant(session, tenant_id)
    return [ApiKeyRead.model_validate(k) for k in await tenants_repo.list_api_keys(session, tenant_id)]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)) -> ApiKeyCreated:
    await _require_tenant(session, tenant_id)
    key, raw = await tenants_repo.create_api_key(session, tenant_id=tenant_id, key_type=ApiKeyTypes.API_SECRET)
    await session.commit()
    return ApiKeyCreated(**ApiKeyRead.model_validate(key).model_dump(), secret=raw)


@router.delete("/api-keys/{key_id}", response_model=ApiKeyRead)
async def revoke_api_key(
    tenant_id: uuid.UUID, key_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiKeyRead:
    key = await tenants_repo.revoke_api_key(session, tenant_id, key_id)
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")
    await session.commit()
    return ApiKeyRead.model_validate(key)
