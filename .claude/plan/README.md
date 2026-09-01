# Implementation Plan — AI Chatbot Platform for Businesses

This directory holds the phase-by-phase implementation plan. Each phase file is
self-contained: goal, prerequisites, data model, API spec, task checklist, test
plan, and explicit out-of-scope items. Build phases in order — each one depends
on tables/endpoints from the previous phases.

## Confirmed tech stack (from `pyproject.toml`)

- **Backend:** FastAPI, single deployable app, modular routers (`/superadmin`,
  `/tenant`, `/bot`, `/auth`, `/widget`)
- **DB:** PostgreSQL + `pgvector` extension, SQLAlchemy 2.0 (async, via
  `psycopg` v3 async driver), Alembic migrations
- **Auth:** JWT (`python-jose`), password hashing (`passlib[bcrypt]`,
  `bcrypt<4.1` pinned)
- **LLM/Embeddings:** OpenAI (`openai` SDK)
- **Document parsing:** `pypdf` (PDF), `python-docx` (DOCX), `beautifulsoup4`
  + `httpx` (URL import), `python-multipart` (uploads)
- **Frontends (Superuser UI + Client Dashboard):** Next.js + TypeScript,
  deployed on Vercel (recommended, not yet committed in code)
- **Channel adapter:** self-hosted n8n (webhook receipt, signature
  verification, per-channel send-message calls)

## Key architecture decisions (carried from design discussion)

| Decision | Resolution |
|---|---|
| Multi-tenancy isolation | Shared Postgres, `tenant_id` on every tenant-scoped table, enforced at app layer (mandatory query filter) + Postgres RLS as defense-in-depth |
| Bot's data access | Bot can **read** Documents + Catalog only. It can **create** leads (write-only — no read/list/update of existing leads, sales, or settings) |
| Superuser vs tenant users | Separate tables (`platform_admins` vs `tenant_users`) — no shared "is_admin" flag that could be misconfigured |
| Onboarding | Superuser creates tenant + invite → tenant activates with temp password → sets own credentials |
| Sales module | No separate sales entity — computed from `leads.status = converted` + manually entered `deal_value` |
| Channel integration | n8n normalizes every channel into `{tenant_id, external_user_id, message}` and calls one internal `/bot/message` endpoint — backend stays channel-agnostic |
| IDs | UUID primary keys on all tenant-scoped tables (non-guessable, avoids enumeration) |
| Payments | Out of scope entirely — bot never touches payment data |

## Code organization conventions

Matches the existing `src/app/` skeleton — put new code in these locations,
not new top-level folders:

```
src/app/
  main.py          # FastAPI() instance + include_router() calls (create in Phase 0)
  core/
    config.py       # pydantic-settings Settings — DB URL, JWT secret, OpenAI key, etc.
    security.py     # password hash/verify, JWT encode/decode, token generation/hashing
    deps.py         # FastAPI dependencies: get_db_session, get_current_platform_admin,
                    #   get_current_tenant_user, get_current_tenant_id, get_current_service_tenant
  db/
    base.py         # Base, TimestampMixin, TenantScopedMixin (already exists)
    session.py      # async engine + AsyncSession factory + get_db_session()
  models/           # SQLAlchemy ORM only, one file per domain area:
                    #   tenants.py, documents.py, catalog.py, conversations.py, leads.py, settings.py
  schemas/          # Pydantic request/response models — filenames mirror models/
  repos/            # query functions — filenames mirror models/; every tenant-scoped
                    #   function takes tenant_id as an explicit argument, never a global query
  services/         # business logic orchestration (email, onboarding, chunking,
                    #   embeddings, publishing, bot_engine, lead_flow, notifications)
  api/
    auth/           # shared tenant-user login/activate/reset endpoints
    superadmin/     # platform admin router(s)
    tenant/         # one router module per dashboard page: documents.py, catalog.py,
                    #   leads.py, settings.py, sales.py
    bot/            # POST /bot/message — only router allowed to import documents/catalog
                    #   repos and the lead *creation* path; never leads-read/sales/settings
    widget/         # POST /widget/session (Phase 9)
database/alembic/   # migrations — script_location points here from alembic.ini at repo root
```

`models/__init__.py` must import every model module (e.g.
`from .tenants import Tenant, PlatformAdmin, ...`) so `Base.metadata` is
complete before Alembic autogenerate runs — it's empty right now, which is a
blocker for Phase 0's first migration.

When a model is tenant-scoped, inherit `TenantScopedMixin` (already defines
`id`, `tenant_id`, `created_at`, `updated_at`) instead of redeclaring those
columns.

## Phases

| Phase | File | Summary |
|---|---|---|
| 0 | [00-foundation.md](00-foundation.md) | Tenancy schema, auth, onboarding/activation flow |
| 1 | [01-superuser-api.md](01-superuser-api.md) | Tenant management endpoints for the Superuser UI |
| 2 | [02-documents-module.md](02-documents-module.md) | Documents CRUD, draft/publish lifecycle, chunk+embed pipeline |
| 3 | [03-catalog-module.md](03-catalog-module.md) | Category tree, products/variants |
| 4 | [04-bot-core-engine.md](04-bot-core-engine.md) | Intent routing, RAG, catalog lookup, session state |
| 5 | [05-leads-module.md](05-leads-module.md) | Dynamic lead schema, capture flow, partial/full leads |
| 6 | [06-client-dashboard.md](06-client-dashboard.md) | Dashboard frontend: Documents/Catalog/Leads pages |
| 7 | [07-settings-module.md](07-settings-module.md) | Bot config, branding, feature toggles, API keys |
| 8 | [08-sales-module.md](08-sales-module.md) | Sales metrics computed from leads |
| 9 | [09-website-widget.md](09-website-widget.md) | Embeddable chat widget |
| 10 | [10-inbox-channel-n8n.md](10-inbox-channel-n8n.md) | Facebook/Instagram inbox integration via n8n |
| 11 | [11-security-hardening.md](11-security-hardening.md) | RLS, rate limiting, secrets, IDOR checks |
| 12 | [12-deployment.md](12-deployment.md) | Staging/production deployment |

## Open items to revisit

- Whether tenant users ever need multiple staff logins (schema in Phase 0
  allows it; not built/enforced beyond a single `owner` role for MVP)
- WhatsApp Business API is noted as a Phase 10 follow-on, not MVP-blocking
