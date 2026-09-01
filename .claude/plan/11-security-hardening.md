# Phase 11 — Security Hardening Pass

## Goal

A dedicated pass before any real tenant/customer traffic — defense-in-depth
on top of the per-phase checks already built in.

## Prerequisites

All prior phases functionally complete.

## Where to implement

| File | Contents |
|---|---|
| `database/alembic/versions/*_add_rls_policies.py` | Raw `op.execute(...)` statements: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;` + `CREATE POLICY ... USING (tenant_id = current_setting('app.current_tenant_id')::uuid);` per tenant-scoped table |
| `src/app/db/session.py` | Add a middleware/dependency that runs `SET LOCAL app.current_tenant_id = :tenant_id` at the start of each request's transaction, right after `get_current_tenant_id`/`get_current_service_tenant`/`get_current_widget_session` resolves the tenant |
| `src/app/core/security.py` | Add Fernet encrypt/decrypt helpers if not already added in Phase 10, sourced from a `fernet_key` setting in `core/config.py` |
| `src/app/core/rate_limit.py` | `slowapi` (or equivalent) limiter setup; apply to `/auth/*`, `/widget/session`, `/bot/message`, webhook endpoints |
| CI config (e.g. `.github/workflows/ci.yml`) | Add a `pip-audit` (or equivalent) step against `pyproject.toml`/`uv.lock` |

## Tasks

**Multi-tenant isolation (defense-in-depth)**
- Enable Postgres Row-Level Security on every tenant-scoped table
- Set `app.current_tenant_id` as a session variable per request (a FastAPI
  middleware/dependency executes `SET LOCAL app.current_tenant_id = ...` at
  the start of each transaction)
- Policies: `USING (tenant_id = current_setting('app.current_tenant_id')::uuid)`
- This catches any application-layer query that forgets a `tenant_id` filter

**Secrets management**
- All API keys (`tenant_api_keys.hashed_secret`), channel access tokens
  (`channel_connections.encrypted_access_token`) — confirm hashing/encryption
  is actually applied, not just planned
- Fernet key (or KMS-backed equivalent) for token encryption lives in a
  secret manager / environment variable, never committed, rotated on a
  documented schedule
- `.env` confirmed in `.gitignore` (already present per repo setup) — audit
  no real secrets ever got committed to git history

**Rate limiting**
- Public/semi-public endpoints: `/widget/session`, `/bot/message` (widget
  path), inbound webhook — add rate limiting (e.g. `slowapi` or at a reverse
  proxy/CDN layer) keyed by IP + site key/tenant to blunt abuse and cost
  overruns on the LLM calls
- Login/activation endpoints rate-limited per IP + email to blunt credential
  stuffing/brute force

**Input validation**
- File upload size/type limits enforced (Phase 2) — confirm actually wired
- Request body size limits at the ASGI/reverse-proxy layer
- Standard Pydantic validation on every endpoint (already structural, audit
  for any raw dict/JSON bypass)

**Dependency/vuln scanning**
- `pip-audit` (or equivalent) in CI against `pyproject.toml`/`uv.lock`
- Pin and review the `bcrypt<4.1` constraint noted in `pyproject.toml` —
  revisit when passlib's bcrypt backend detection is fixed upstream

**Access control review checklist (manual, run once + at each future PR)**
- Every tenant-scoped repository function requires `tenant_id` as an explicit
  argument (Phase 0 convention) — grep for any query missing it
- `/bot` router has zero import path to Leads (read), Sales, or Settings
  modules (Phase 5 requirement)
- JWT `tenant_id`/`scope` claims are the only source of tenant identity in
  protected routes — no route trusts a client-supplied `tenant_id`

## Test plan

- Attempt cross-tenant reads via crafted requests (valid JWT for tenant A,
  guessed/enumerated ID for tenant B's resource) → blocked at the app layer;
  then temporarily bypass the app-layer filter in a test to confirm RLS
  alone still blocks it
- Oversized file upload → rejected before parsing begins
- Expired/tampered/invalid JWT → 401 on every protected route, including
  `/bot/message`'s widget-session path
- Rate limit triggers `429` after the configured threshold on login and
  widget session endpoints
- Tampered webhook signature → rejected before any tenant resolution happens

## Out of scope

- Formal third-party penetration test (recommended before a large client
  goes live, but a separate engagement, not part of this build phase)
- SOC2/compliance program work
