from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# prepare_threshold=None disables psycopg3's automatic server-side prepared
# statements. Required when DATABASE_URL points at a pgbouncer/Supavisor
# transaction-mode pooler (e.g. Supabase's transaction pooler): each
# transaction can land on a different physical backend connection there, so
# a statement prepared on one backend can go missing on the next, causing
# intermittent "prepared statement ... does not exist" errors. Harmless
# against a direct/session-mode connection too, just a little less caching.
engine = create_async_engine(settings.database_url, pool_pre_ping=True, connect_args={"prepare_threshold": None})
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
