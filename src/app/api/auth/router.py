from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.db.session import get_db_session
from app.repos import tenants as tenants_repo
from app.schemas.tenants import (
    CompleteActivationRequest,
    LoginRequest,
    PasswordResetRequest,
    RequestPasswordResetRequest,
    TokenResponse,
    VerifyActivationRequest,
)
from app.services import onboarding
from app.services.email import get_email_sender

router = APIRouter(prefix="/auth", tags=["auth"])
_email_sender = get_email_sender()


@router.post("/tenant/login", response_model=TokenResponse)
async def tenant_login(
    payload: LoginRequest, session: AsyncSession = Depends(get_db_session)
) -> TokenResponse:
    admin = await tenants_repo.get_tenant_admin_by_username(session, payload.username)
    if admin is None or not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    tenant = await tenants_repo.get_tenant_by_id(session, admin.tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant is suspended")

    token = create_access_token({"sub": str(tenant.id), "scope": "tenant"})
    return TokenResponse(access_token=token)


@router.post("/activate", status_code=status.HTTP_204_NO_CONTENT)
async def verify_activation(
    payload: VerifyActivationRequest, session: AsyncSession = Depends(get_db_session)
) -> None:
    """Step 1: confirm identity via email + the raw invite token. No side
    effects -- lets the client validate before showing the credentials
    form. The client resubmits the same email/token in step 2."""
    try:
        await onboarding.verify_activation(session, payload.token, payload.email)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/activate/set-credentials", status_code=status.HTTP_204_NO_CONTENT)
async def complete_activation(
    payload: CompleteActivationRequest, session: AsyncSession = Depends(get_db_session)
) -> None:
    """Step 2: resubmit the same invite token from step 1 (already held by
    the client, not re-entered by the user), plus a username/password --
    what the tenant will use for every login from here on via
    POST /auth/tenant/login, which the client should call next."""
    try:
        await onboarding.complete_activation(session, payload.token, payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "username already taken") from exc


@router.post("/request-password-reset", status_code=status.HTTP_204_NO_CONTENT)
async def request_password_reset(
    payload: RequestPasswordResetRequest, session: AsyncSession = Depends(get_db_session)
) -> None:
    await onboarding.request_password_reset(session, _email_sender, payload.username)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: PasswordResetRequest, session: AsyncSession = Depends(get_db_session)
) -> None:
    try:
        await onboarding.reset_password(session, payload.token, payload.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
