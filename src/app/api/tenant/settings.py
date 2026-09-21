"""Tenant dashboard settings. Writes accept ONLY tenant-settable fields
(schemas.settings.TenantSettingsUpdate forbids everything else); the
admin-set half is returned read-only as `capabilities`. There is deliberately
no API-key or widget-key management here -- those are admin-only."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant_id
from app.db.session import get_db_session
from app.repos import settings as settings_repo
from app.repos import settings_read
from app.schemas.settings import (
    CapabilitiesRead,
    TenantSettingsRead,
    TenantSettingsResponse,
    TenantSettingsUpdate,
)
from app.services import settings_resolver

router = APIRouter(prefix="/tenant/settings", tags=["settings"])

# columns that are nullable -- an explicit `null` clears them; for every
# other field null is a 422 rather than a DB IntegrityError
_NULLABLE = {"bot_name", "welcome_message", "fallback_message", "custom_instructions", "min_order_value"}


async def _response(session: AsyncSession, tenant_id: uuid.UUID) -> TenantSettingsResponse:
    tenant_row = await settings_read.get_tenant_settings(session, tenant_id)
    admin_row = await settings_read.get_admin_settings(session, tenant_id)
    if tenant_row is None or admin_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "settings not found for this tenant")
    return TenantSettingsResponse(
        settings=TenantSettingsRead.model_validate(tenant_row),
        capabilities=CapabilitiesRead.model_validate(admin_row),
    )


@router.get("", response_model=TenantSettingsResponse)
async def get_settings(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSettingsResponse:
    return await _response(session, tenant_id)


@router.patch("", response_model=TenantSettingsResponse)
async def update_settings(
    payload: TenantSettingsUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> TenantSettingsResponse:
    fields = payload.model_dump(exclude_unset=True)
    nulled = [k for k, v in fields.items() if v is None and k not in _NULLABLE]
    if nulled:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"cannot set to null: {sorted(nulled)}")

    current = await settings_read.get_tenant_settings(session, tenant_id)
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "settings not found for this tenant")
    delivery = fields.get("delivery_enabled", current.delivery_enabled)
    pickup = fields.get("pickup_enabled", current.pickup_enabled)
    if not delivery and not pickup:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "at least one of delivery_enabled / pickup_enabled must stay on (turn ordering off instead)",
        )

    row = await settings_repo.update_tenant_settings(session, tenant_id, **fields)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "settings not found for this tenant")
    await session.commit()
    settings_resolver.invalidate(tenant_id)
    return await _response(session, tenant_id)
