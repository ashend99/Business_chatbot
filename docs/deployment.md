# Deployment runbook

How the platform is deployed and operated. Config lives in the repo
(`Dockerfile`, `railway.json`, `.github/workflows/ci.yml`); this document
covers the one-time account setup and the day-to-day flow.

## Topology

| Part | Where | Deploys from |
|---|---|---|
| FastAPI backend | Railway (Docker image from `Dockerfile`) | `main`, after CI passes |
| `client_ui` (tenant dashboard) | Vercel project, root dir `client_ui` | `main` |
| `admin_ui` (platform admin) | Vercel project, root dir `admin_ui` | `main` |
| Postgres + pgvector | Supabase (a **separate project** from the dev database) | -- |

The browser never calls the backend directly: both Next.js apps call it
server-side (route handlers / server components). So the backend needs no
CORS configuration, and none is set -- keep it that way.

## Flow of a change

1. Push (or merge) to `main`.
2. GitHub Actions (`ci.yml`) runs: backend lint/types/tests, the Docker image
   build + smoke test, and both frontends' lint/tsc/build.
3. Railway waits for CI to pass, builds the image, runs
   `alembic upgrade head` (pre-deploy), then swaps traffic once `/health`
   answers. If the migration fails the deploy stops and the previous version
   keeps serving.
4. Vercel builds and deploys each frontend.

---

## One-time setup

### 1. Production database (Supabase)

1. Create a **new** Supabase project for production (don't reuse the dev
   one). Pick the region closest to your customers, and use the same region
   for Railway.
2. Database → Extensions → enable **vector** (the first migration also runs
   `CREATE EXTENSION IF NOT EXISTS vector`).
3. Project Settings → Database → Connection string, copy two URLs and change
   the scheme to `postgresql+psycopg://`:
   - **Transaction pooler** (port `6543`) → `DATABASE_URL` (the app; the code
     already handles pgbouncer via `prepare_threshold=None`).
   - **Session pooler / direct** (port `5432`) → `MIGRATION_DATABASE_URL`
     (schema changes shouldn't go through the transaction pooler).
   URL-encode special characters in the password (`@` → `%40`, etc.).

### 2. Backend (Railway)

1. New Project → Deploy from GitHub repo → this repository. Railway picks up
   `railway.json` (Dockerfile build, pre-deploy migration, `/health` check).
2. Service → Settings:
   - Branch: `main`; enable **Wait for CI**.
   - Networking → Generate Domain (or add a custom one, e.g. `api.yourdomain.com`).
3. Service → Variables:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` (startup refuses dev placeholders -- see `core/config.py`) |
| `DATABASE_URL` | Supabase transaction pooler URL (:6543) |
| `MIGRATION_DATABASE_URL` | Supabase session/direct URL (:5432) |
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` | your admin login -- a strong, unique password |
| `OPENAI_API_KEY` | production key (consider a separate OpenAI project with a spend limit) |
| `EMAIL_BACKEND` | `smtp` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` | your mail provider |
| `CLIENT_DASHBOARD_URL` | public URL of `client_ui` (used in invite/reset emails) |
| `SENTRY_DSN` | from Sentry (optional, see Operations) |

`PORT` is injected by Railway -- don't set it.

4. Deploy, then check `https://<backend-domain>/health/ready` returns
   `{"status":"ok","database":"ok"}`.

### 3. Frontends (Vercel)

Create **two** projects from the same repository:

| Project | Root Directory | Environment variables |
|---|---|---|
| client dashboard | `client_ui` | `API_BASE_URL=https://<backend-domain>` |
| admin | `admin_ui` | `API_BASE_URL=https://<backend-domain>` |

- Framework preset: Next.js (auto-detected). Production branch: `main`.
- Settings → Git → **Ignored Build Step**: `git diff --quiet HEAD^ HEAD -- .`
  so a backend-only change doesn't rebuild the frontends.
- **Do not set `BOT_API_SECRET` on the production `client_ui`.** `/widget-test`
  is a public, unauthenticated debug page that chats using that tenant key --
  in production it would let anyone spend that tenant's LLM budget. Without
  the variable the page just reports it isn't configured.
- Consider Vercel Deployment Protection on the `admin_ui` project so the
  admin login page isn't publicly reachable.

### 4. First-run checks

1. Admin UI → log in with `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD`.
2. Onboard a test tenant → the invite email arrives (proves SMTP).
3. Follow the invite, set credentials, log in to the client dashboard.
4. Add a catalog item and a document, publish the document.
5. Admin UI → issue an `api_secret` key for the tenant and call
   `POST /bot/message` with it (`X-Api-Key` header) -- confirm a reply, then
   check the Conversations page shows it.

---

## Rollback

- **Backend**: Railway → Deployments → pick the last good one → Redeploy.
- **Frontends**: Vercel → Deployments → last good one → Promote to Production.
- **Migrations are never rolled back automatically.** Write them to be
  backwards compatible (add columns/tables first, remove old ones in a later
  release) so the previous app version still runs against the new schema.

## Staging (later)

When you want one: a `develop` branch, a second Railway environment and a
second Supabase project, with Vercel preview deployments pointing at the
staging backend. The same `railway.json` and CI apply unchanged.
