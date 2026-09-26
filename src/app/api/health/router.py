"""Unauthenticated health checks for the hosting platform and uptime monitors.

`/health` is liveness only (the process is up and serving) -- deliberately no
DB call, so a brief database blip doesn't make the host restart a healthy
container. `/health/ready` also checks the database, for readiness gates and
monitoring.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness(session: AsyncSession = Depends(get_db_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable") from exc
    return {"status": "ok", "database": "ok"}
