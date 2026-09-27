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

## Dev environment (current setup)

Until production is set up, only the **`dev` branch** is deployed, against
the **existing Supabase project** (the same database as local `.env`).
`main` is not deployed. Follow the one-time setup below with these
differences:

| Setting | Dev environment value |
|---|---|
| Railway branch | `dev` (still with **Wait for CI**) |
| Vercel production branch (both projects) | `dev` |
| `ENVIRONMENT` | `staging` -- secrets are still checked (it's on a public URL); console email is allowed |
| `DATABASE_URL` | the one already in your local `.env` |
| `MIGRATION_DATABASE_URL` | optional: the same project's session pooler (`:5432`) URL |
| `JWT_SECRET` | a **new** random value, not the local one |
| `EMAIL_BACKEND` | `console` is fine (emails then only appear in Railway logs) or `smtp` |
| `CLIENT_DASHBOARD_URL` | the dev `client_ui` Vercel URL |

The flow is the same as above with `dev` in place of `main`: push to `dev` →
CI → Railway deploys the backend (running `alembic upgrade head` on the
existing Supabase first) → Vercel deploys both frontends.

Things to know about sharing one database between your local machine and
the deployed dev backend:

- **Migrations**: the deploy migrates the shared DB. Don't run a migration
  locally from a branch that isn't merged into `dev` -- the deployed code
  would then run against a schema it doesn't know.
- **Settings cache**: each running backend caches tenant settings for 30s
  (see `services/settings_resolver.py`). A settings change made through your
  local server can take up to 30s to reach the deployed one, and vice versa.
- **Data**: local testing, the eval harness and the deployed site all see
  and change the same tenants, leads and orders.
- **`/widget-test`**: fine to use in dev with `BOT_API_SECRET` set on the dev
  `client_ui`, but the page is public -- turn on Vercel **Deployment
  Protection** for the dev projects so strangers can't reach it (or the
  dashboards).

Moving to production later: create the new Supabase project, point Railway
and Vercel at `main`, and set `ENVIRONMENT=production` -- the rest of this
runbook.

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

## Dev and production side by side (later)

Once production exists, keep the `dev` deployment as staging: a second
Railway environment on `dev` and a production one on `main`, each with its
own Supabase project. Merge `dev` → `main` to release. The same
`railway.json` and CI apply unchanged.
