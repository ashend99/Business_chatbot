import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db_session
from app.repos import tenants as tenants_repo

bearer_scheme = HTTPBearer()


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
