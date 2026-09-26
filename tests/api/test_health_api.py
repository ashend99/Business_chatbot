"""Health endpoints used by the hosting platform (see Dockerfile / railway.json)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.main import app


async def test_liveness_needs_no_auth(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_checks_the_database(client) -> None:
    response = await client.get("/health/ready")
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_readiness_reports_database_outage(client) -> None:
    class BrokenSession(AsyncSession):
        async def execute(self, *args, **kwargs):
            raise ConnectionError("db down")

    async def broken_session():
        yield BrokenSession()

    app.dependency_overrides[get_db_session] = broken_session
    try:
        response = await client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    # liveness is unaffected by the database
    assert (await client.get("/health")).status_code == 200
