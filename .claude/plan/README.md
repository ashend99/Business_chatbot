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
