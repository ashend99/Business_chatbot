import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.api.auth.router import router as auth_router
from app.api.bot.router import router as bot_router
from app.api.superadmin.auth import router as superadmin_auth_router
from app.api.superadmin.tenants import router as superadmin_tenants_router
from app.api.tenant.catalog import router as tenant_catalog_router
from app.api.tenant.documents import router as tenant_documents_router
from app.components.rag import get_rag
from app.core.config import settings
from common import configure_logging

# must run before uvicorn starts serving requests -- see
# common/logging_setup.py for why this is needed at all: without it,
# `logger.info(...)` records are silently dropped below WARNING everywhere.
configure_logging()

# psycopg's async mode can't use Windows' default ProactorEventLoop -- only
# effective if set before uvicorn creates its event loop, i.e. before
# `import app.main` happens. The `uvicorn app.main:app` CLI form imports this
# module *inside* asyncio.run(), too late for this to take effect on Windows;
# use `python -m app.main` for local dev instead (see __main__ block below).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

tags_metadata = [
    {"name": "auth", "description": "Tenant login, invite activation, and password reset."},
    {"name": "superadmin", "description": "Platform admin login and tenant onboarding/management."},
    {"name": "documents", "description": "Tenant document ingestion: draft/publish lifecycle, chunk+embed pipeline."},
    {"name": "catalog", "description": "Tenant category tree, products, and variants (structured, always-accurate pricing/stock)."},
    {"name": "bot", "description": "Internal service endpoint -- the LangGraph agent, called by n8n/the widget backend."},
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # construct the singleton RAG instance eagerly at startup (fails fast on
    # a bad config, e.g. missing OPENAI_API_KEY, rather than on first use) --
    # every later get_rag() call, from any module, returns this same instance
    get_rag()

    # AsyncPostgresSaver wants a plain psycopg conn string, not SQLAlchemy's
    # dialect-prefixed one -- its checkpoint tables are separate from (and
    # not managed by) our own Alembic migrations.
    conn_string = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    # Built manually rather than via AsyncPostgresSaver.from_conn_string,
    # which hardcodes prepare_threshold=0 (prepare every statement
    # immediately) -- the wrong choice against a pgbouncer/Supavisor
    # transaction-mode pooler, where a statement prepared on one backend
    # connection can vanish on the next transaction's connection. See
    # db/session.py's comment for the full explanation.
    async with await AsyncConnection.connect(
        conn_string, autocommit=True, prepare_threshold=None, row_factory=dict_row
    ) as conn:
        checkpointer = AsyncPostgresSaver(conn=conn)
        await checkpointer.setup()
        app.state.checkpointer = checkpointer
        yield


app = FastAPI(
    title="Business Chatbot Platform",
    description="RAG-powered chatbot platform API -- tenant dashboard, superadmin, and bot endpoints.",
    version="0.1.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(superadmin_auth_router)
app.include_router(superadmin_tenants_router)
app.include_router(tenant_documents_router)
app.include_router(tenant_catalog_router)
app.include_router(bot_router)

if __name__ == "__main__":
    import uvicorn

    # loop="none" is required on Windows: uvicorn's own "asyncio" loop factory
    # forces ProactorEventLoop unconditionally, which silently overrides the
    # policy set above. loop="none" skips that factory so our policy actually
    # takes effect via asyncio.new_event_loop().
    uvicorn.run(app, host="127.0.0.1", port=8000, loop="none")
