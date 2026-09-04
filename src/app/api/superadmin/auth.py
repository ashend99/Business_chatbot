from fastapi import APIRouter, HTTPException, status

from app.core.security import create_access_token, verify_superadmin_credentials
from app.schemas.tenants import SuperadminLoginRequest, TokenResponse

router = APIRouter(prefix="/superadmin/auth", tags=["superadmin"])


@router.post("/login", response_model=TokenResponse)
async def superadmin_login(payload: SuperadminLoginRequest) -> TokenResponse:
    if not verify_superadmin_credentials(payload.email, payload.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    token = create_access_token({"sub": "superadmin", "scope": "platform_admin"})
    return TokenResponse(access_token=token)
