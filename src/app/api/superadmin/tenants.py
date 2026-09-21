import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_platform_admin
from app.db.session import get_db_session
from app.repos import tenants as tenants_repo
from app.schemas.tenants import (
    TenantCreate,
    TenantDetail,
    TenantListItem,
    TenantListResponse,
    TenantRead,
    TenantUpdate,
)
from app.services import onboarding
from app.services.email import get_email_sender
from app.services.onboarding import TenantSuspendedError

router = APIRouter(
    prefix="/superadmin/tenants",
    tags=["superadmin"],
    dependencies=[Depends(get_current_platform_admin)],
)


def _admin_overrides(payload: TenantCreate) -> dict:
    """The optional admin_settings block minus currency (already a required
    top-level field of TenantCreate) as kwargs for create_default_settings."""
    overrides = payload.admin_settings.model_dump(exclude_unset=True) if payload.admin_settings else {}
    overrides.pop("currency_code", None)
    return overrides


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, session: AsyncSession = Depends(get_db_session)) -> TenantRead:
    try:
        tenant = await onboarding.onboard_tenant(
            session,
            get_email_sender(),
            name=payload.name,
            slug=payload.slug,
            email=payload.email,
            contact_person=payload.contact_person,
            contact_number=payload.contact_number,
            address=payload.address,
            currency_code=payload.currency_code,
            timezone=payload.timezone,
            admin_settings=_admin_overrides(payload),
        )
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "slug or email already in use") from exc
    return TenantRead.model_validate(tenant)


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    is_active: bool | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> TenantListResponse:
    items, total = await tenants_repo.list_tenants(
        session, is_active=is_active, search=search, page=page, page_size=page_size
    )
    return TenantListResponse(
        items=[TenantListItem.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{tenant_id}", response_model=TenantDetail)
async def get_tenant(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)) -> TenantDetail:
    tenant = await tenants_repo.get_tenant_by_id(session, tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")

    admin = await tenants_repo.get_tenant_admin_by_tenant_id(session, tenant_id)
    return TenantDetail(
        **TenantRead.model_validate(tenant).model_dump(),
        activated=admin is not None,
        admin_username=admin.username if admin else None,
    )


@router.patch("/{tenant_id}", response_model=TenantRead)
async def update_tenant(
    tenant_id: uuid.UUID, payload: TenantUpdate, session: AsyncSession = Depends(get_db_session)
) -> TenantRead:
    try:
        tenant = await tenants_repo.update_tenant(session, tenant_id, **payload.model_dump(exclude_unset=True))
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "email already in use") from exc
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    await session.commit()
    return TenantRead.model_validate(tenant)


@router.post("/{tenant_id}/resend-invite", status_code=status.HTTP_204_NO_CONTENT)
async def resend_invite(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)) -> None:
    try:
        await onboarding.resend_invite(session, get_email_sender(), tenant_id)
    except TenantSuspendedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/{tenant_id}/suspend", response_model=TenantRead)
async def suspend_tenant(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)) -> TenantRead:
    tenant = await tenants_repo.set_tenant_active(session, tenant_id, False)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    await session.commit()
    return TenantRead.model_validate(tenant)


@router.post("/{tenant_id}/reactivate", response_model=TenantRead)
async def reactivate_tenant(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)) -> TenantRead:
    tenant = await tenants_repo.set_tenant_active(session, tenant_id, True)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    await session.commit()
    return TenantRead.model_validate(tenant)
