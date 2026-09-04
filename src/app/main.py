import asyncio
import sys

from fastapi import FastAPI

from app.api.auth.router import router as auth_router
from app.api.superadmin.auth import router as superadmin_auth_router
from app.api.superadmin.tenants import router as superadmin_tenants_router
from app.api.tenant.documents import router as tenant_documents_router
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
]

app = FastAPI(
    title="Business Chatbot Platform",
    description="RAG-powered chatbot platform API -- tenant dashboard, superadmin, and bot endpoints.",
    version="0.1.0",
    openapi_tags=tags_metadata,
)

app.include_router(auth_router)
app.include_router(superadmin_auth_router)
app.include_router(superadmin_tenants_router)
app.include_router(tenant_documents_router)

if __name__ == "__main__":
    import uvicorn

    # loop="none" is required on Windows: uvicorn's own "asyncio" loop factory
    # forces ProactorEventLoop unconditionally, which silently overrides the
    # policy set above. loop="none" skips that factory so our policy actually
    # takes effect via asyncio.new_event_loop().
    uvicorn.run(app, host="127.0.0.1", port=8000, loop="none")
