# Phase 13 — Production readiness (tests → CI → Docker → deploy)

## Goal

Pause feature work and build the production flow around the working v0.1
system: an automated test suite, CI on every PR, a backend container image,
and a staging/production deployment. Supersedes the ordering (not the
content) of [11-security-hardening.md](11-security-hardening.md) and
[12-deployment.md](12-deployment.md).

## Target topology

| Part | Where |
|---|---|
| `client_ui`, `admin_ui` | Vercel — two projects from the same repo, root dir per app |
| FastAPI backend | Container host (Railway first choice; Render/Fly.io/VPS also fine) |
| Postgres + pgvector | Supabase or Neon — pooled URL for the app, direct URL for migrations |

The backend stays off Vercel: `lifespan` holds a long-lived checkpointer
connection and builds the RAG singleton, bot turns and document publishing
(embedding runs inside the request) can be slow, the dependency bundle is
large, and the settings cache is in-process.

## Order of work

Tests (1) → CI (2) makes tests useful immediately. Docker (3) is then
validated by CI as it's built, and deployment (4) only happens once every
change is automatically checked.

---

## Phase 1 — Tests

**Principles**
- Real Postgres + pgvector, not mocks. The bugs this codebase has had were
  DB-behaviour bugs (races, status transitions).
- Zero network: `embed_texts` is faked with deterministic vectors; the chat
  model is replaced with a scripted fake. Fast, free, deterministic.
- The `eval/` harness stays separate — real LLM, costs money, manual/nightly.

**1.0 Infrastructure**
- Separate test database (`business_chatbot_test`), via `TEST_DATABASE_URL`
  (defaults derived from `DATABASE_URL` with a `_test` suffix).
- Safety guard: refuse to run unless the DB name contains `test`.
- `conftest.py`: Windows selector loop policy, schema created once per
  session, per-test data cleanup, factory helpers (`make_tenant`,
  `make_catalog`, lead fields).
- `httpx.AsyncClient` over `ASGITransport` for API tests (no lifespan; an
  in-memory checkpointer is set on `app.state`).

**1.1 Architecture tests**
- AST-scan `api/bot/router.py`, `bot_engine.py`, `bot_tools.py`: no `*_admin`
  import, no settings write module import.

**1.2 Unit tests (no DB)**
- `money`, `resolve_bot_status`, the three reply guardrails,
  `prompt_builder`, the settings effective-toggle rule, `chunking`,
  `file_parsing`, security helpers.

**1.3 Repo/DB tests**
- Tenant isolation across leads, orders, catalog, documents, conversations.
- Orders: server-side pricing, every `confirm_order` error + happy path,
  `pending_confirmation`.
- Leads: upsert-by-conversation, concurrent-call race (advisory lock),
  lead↔order linking in both orders.
- Catalog: multi-word search, subtree browse.
- Documents: active window, safe publish (old chunks survive a failed embed).

**1.4 API tests**
- Auth (tenant/superadmin), cross-tenant 404s, settings split 422,
  `/bot/message` (channel 403, `bot_enabled=false`, bad key), staff order
  transitions.

**1.5 Agent tests with a scripted fake LLM**
- Full turns through `handle_message`: tool call → DB row → guardrails.

**Frontends:** lint + `tsc --noEmit` + `next build` only, for now.

**Exit:** `pytest` green locally, offline, in reasonable time.

## Phase 2 — CI (GitHub Actions)

- Backend job: `uv sync` → `ruff check` → `mypy` → `pytest` against a
  `pgvector/pgvector` service container.
- Frontend job (matrix: `client_ui`, `admin_ui`): `npm ci` → lint → `tsc` →
  `build`.
- Trigger on PRs to `develop`/`main`; branch protection on `main`.

## Phase 3 — Docker (backend only)

- Multi-stage `Dockerfile` (`uv`, non-root user), plain `uvicorn` on Linux
  (the Windows selector-loop workaround is a no-op there).
- `docker-compose.yml` for local dev: backend + Postgres/pgvector.
- Migrations as a release step (`alembic upgrade head`), not on startup.
- `/health` endpoint for host health checks.
- Image build added to CI.

## Phase 4 — Deploy

- DB: Supabase/Neon with pgvector; pooled URL for the app (code already
  handles pgbouncer via `prepare_threshold=None`), direct URL for migrations.
- Backend on Railway, migration as pre-deploy command, secrets in its env.
- Frontends: two Vercel projects; backend URL + `BOT_API_SECRET` as env vars.
- Environments: `develop` → staging, `main` → production, separate DBs.
- CORS locked to the Vercel domains.

## Phase 5 — Operate

- Sentry (backend + both frontends).
- Automated DB backups plus one tested restore.
- Before real traffic (code, not infra): rate limiting on `/bot/message` and
  enforcing `monthly_message_limit` — protects against runaway LLM spend.
