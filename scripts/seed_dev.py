"""One-off script to seed local dev data. Run with: python scripts/seed_dev.py"""

import asyncio
import sys

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models import Tenant, TenantAdmin

# psycopg's async mode can't run on Windows' default ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "changeme123"


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        tenant = Tenant(
            name="Demo Business",
            slug="demo-business",
            email="demo@example.com",
            contact_person="Demo Owner",
        )
        session.add(tenant)
        await session.flush()  # populate tenant.id before creating the admin row

        admin = TenantAdmin(
            tenant_id=tenant.id,
            username=DEMO_USERNAME,
            hashed_password=hash_password(DEMO_PASSWORD),
        )
        session.add(admin)
        await session.commit()

    print(f"Seeded tenant '{tenant.name}' (slug={tenant.slug})")
    print(f"Login: username={DEMO_USERNAME!r} password={DEMO_PASSWORD!r}")


if __name__ == "__main__":
    asyncio.run(seed())
