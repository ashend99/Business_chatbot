import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, hash_token
from app.db.session import get_db_session
from app.models.tenants import ApiKeyTypes
from app.repos import tenants as tenants_repo

bearer_scheme = HTTPBearer()
api_key_header = APIKeyHeader(name="X-Api-Key")


def _decode_or_401(credentials: HTTPAuthorizationCredentials) -> dict:
    try:
        return decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token") from exc


async def get_current_platform_admin(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> None:
    claims = _decode_or_401(credentials)
    if claims.get("scope") != "platform_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a platform admin")


async def get_current_tenant_id(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> uuid.UUID:
    claims = _decode_or_401(credentials)
    if claims.get("scope") != "tenant":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a tenant token")

    tenant_id = uuid.UUID(claims["sub"])
    tenant = await tenants_repo.get_tenant_by_id(session, tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant is suspended")
    return tenant_id


async def get_current_service_tenant(
    api_key: Annotated[str, Depends(api_key_header)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> uuid.UUID:
    """Auth for internal service callers (n8n, the widget backend) hitting
    /bot/message -- a tenant's api_secret key via X-Api-Key, not a JWT."""
    key = await tenants_repo.get_api_key_by_hash(session, hash_token(api_key))
    if key is None or key.key_type != ApiKeyTypes.API_SECRET or key.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked api key")

    tenant = await tenants_repo.get_tenant_by_id(session, key.tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant is suspended")
    return key.tenant_id
