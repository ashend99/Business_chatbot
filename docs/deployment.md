# Deployment runbook

How the platform is deployed. Config lives in the repo (`Dockerfile`,
`render.yaml`, `.github/workflows/ci.yml`); this document covers the
one-time account setup and the day-to-day flow.

## What runs where (dev environment -- the current setup)

| Part | Where | Deploys from |
|---|---|---|
| FastAPI backend | **Render**, free plan (Docker image from `Dockerfile`, settings in `render.yaml`) | branch `dev`, after CI passes |
| `admin_ui` (platform admin) | **Vercel** project, root directory `admin_ui` | branch `dev` |
| `client_ui` (tenant dashboard) | **Vercel** project, root directory `client_ui` | branch `dev` |
| Postgres + pgvector | the **existing Supabase project** (same database as local `.env`) | -- |

`main` is not deployed yet. The browser never calls the backend directly
(both Next.js apps call it server-side), so the backend needs no CORS.

## Flow of a change

1. Push to `dev`.
2. GitHub Actions (`ci.yml`) runs: backend lint/types/tests, the Docker image
   build + smoke test, and both frontends' lint/type-check/build.
3. Render waits for CI to pass (`autoDeployTrigger: checksPass`), builds the
   image and starts it. On start the container runs `alembic upgrade head`
   (`RUN_MIGRATIONS_ON_START=1`, because the free plan has no pre-deploy
   hook), then serves; Render switches traffic once `/health` answers. A
   failed migration stops the new container and the previous one keeps
   serving. Commits that only touch the frontends don't rebuild the backend.
4. Vercel builds and deploys each frontend (Vercel does not wait for CI).

---

## One-time setup, step by step

Do these in order. You'll need: your GitHub login, your local `.env` (for
two values), and about 30 minutes.

### Step 1 -- Supabase: nothing to create, just check one thing

The dev environment reuses your existing Supabase project, so there is no new
database. Open your local `.env` and look at `DATABASE_URL`:

- It must use the **pooler** host, like
  `...@aws-0-<region>.pooler.supabase.com:6543/postgres`. Yours does.
- Not the direct host `db.<project>.supabase.co` -- that one is IPv6-only and
  Render can't reach it.

Keep `.env` open; Step 2 copies `DATABASE_URL` and `OPENAI_API_KEY` from it.

### Step 2 -- Render: the backend

1. Go to <https://render.com>, sign up / log in **with GitHub**, and allow
   Render access to the `Business_chatbot` repository.
2. **New → Blueprint**. Pick the `Business_chatbot` repo and branch **`dev`**.
   Render reads `render.yaml` and shows one service,
   `business-chatbot-backend-dev`.
3. Render asks for the values marked secret in `render.yaml`. Fill in:

   | Variable | What to enter |
   |---|---|
   | `DATABASE_URL` | copy the whole value from your local `.env` |
   | `OPENAI_API_KEY` | copy from your local `.env` |
   | `SUPERADMIN_EMAIL` | the email you'll log into the admin UI with |
   | `SUPERADMIN_PASSWORD` | a new strong password (write it down) |
   | `CLIENT_DASHBOARD_URL` | `https://example.com` for now -- you'll fix it in Step 5 |

   The others are set automatically: `ENVIRONMENT=staging`,
   `EMAIL_BACKEND=console`, `RUN_MIGRATIONS_ON_START=1`, and a random
   `JWT_SECRET`.
4. Click **Apply**. The first build takes ~5-10 minutes (Logs tab).
   When it's done the logs end with something like
   `Uvicorn running on http://0.0.0.0:10000`.
5. Copy the service URL from the top of its page (e.g.
   `https://business-chatbot-backend-dev.onrender.com`) and open
   `<that URL>/health/ready` in the browser. Expected:
   `{"status":"ok","database":"ok"}`.
6. Service → **Settings → Build & Deploy → Auto-Deploy**: check it says
   **After CI Checks Pass** (set from `render.yaml`).

Free-plan behaviour to expect: the service **sleeps after ~15 minutes idle**,
and the first request afterwards takes ~1 minute to wake it (the dashboards
will look slow or time out once, then work). 512 MB memory.

### Step 3 -- Vercel: the admin UI

1. Go to <https://vercel.com>, sign up / log in **with GitHub**.
2. **Add New → Project → Import** the `Business_chatbot` repository.
3. On the configure screen:
   - Project Name: e.g. `business-chatbot-admin-dev`
   - **Root Directory → Edit → `admin_ui`**
   - Framework Preset: Next.js (detected automatically)
   - **Environment Variables**: `API_BASE_URL` = the Render URL from Step 2.5
     (no trailing slash)
4. Click **Deploy**. (This very first build comes from the repository's
   default branch; the next step moves it to `dev`.)
5. Project → **Settings → Environments → Production → Branch Tracking**
   (older UI: Settings → Git → Production Branch): set it to **`dev`**, save.
6. **Deployments → Create Deployment**, enter branch `dev`, deploy -- or just
   wait for your next push to `dev`.
7. Settings → **Git → Ignored Build Step** → "Custom" command:
   `git diff --quiet HEAD^ HEAD -- .` (skips rebuilding when a commit didn't
   touch `admin_ui`).
8. Settings → **Deployment Protection**: turn on Vercel Authentication if
   your plan allows it for this deployment, so only you can open it.

### Step 4 -- Vercel: the client dashboard

Repeat Step 3 as a **second project** with:

- Project Name: e.g. `business-chatbot-client-dev`
- **Root Directory: `client_ui`**
- Environment Variables:
  - `API_BASE_URL` = the Render URL
  - `BOT_API_SECRET` = only if you want `/widget-test`: copy the value from
    your local `client_ui/.env.local` (it's a key already stored in the
    shared database, so it works as is)
- Same branch (`dev`), Ignored Build Step and Deployment Protection settings.
  `/widget-test` is public, which is why protection matters here.

### Step 5 -- Tell the backend where the dashboard lives

Render → the backend service → **Environment** → edit `CLIENT_DASHBOARD_URL`
to the client dashboard's Vercel URL (e.g.
`https://business-chatbot-client-dev.vercel.app`) → **Save**. Render restarts
the service. (This link goes into invite and password-reset emails.)

### Step 6 -- Check everything end to end

1. Admin UI URL → log in with `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD`
   from Step 2 → you see the existing tenants.
2. Client dashboard URL → log in with your usual dev tenant login → you see
   the same data as locally (it's the same database).
3. Optional: `<client URL>/widget-test` → send a message → a reply comes
   back, and the conversation shows up on the Conversations page.

If a page errors or spins the first time, the Render service was probably
asleep -- wait a minute and reload.

---

## Things to know about sharing the Supabase database

- **Migrations**: every backend start runs `alembic upgrade head` on the
  shared database. Don't run a migration locally from a branch that isn't
  merged into `dev` -- the deployed code would then run against a schema it
  doesn't know.
- **Settings cache**: each running backend caches tenant settings for 30s. A
  settings change made through your local server can take up to 30s to reach
  the deployed one, and vice versa.
- **Data**: local testing, the eval harness and the deployed site all see and
  change the same tenants, leads and orders.
- **Emails**: with `EMAIL_BACKEND=console` emails aren't sent; they appear in
  Render's Logs tab (e.g. an invite token when onboarding a tenant).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Render deploy fails with `unsafe staging configuration: ...` | the message names the variable -- a placeholder (`CHANGE_ME`) or too-short secret; fix it under Environment |
| Render logs: can't connect to the database / "Network is unreachable" | `DATABASE_URL` uses the direct `db.<project>.supabase.co` host -- use the pooler URL from `.env` |
| Render never deploys after a push | CI failed (GitHub → Actions), or Auto-Deploy isn't "After CI Checks Pass" |
| Blueprint rejected when applying `render.yaml` | Render's spec changed -- remove the reported field and set the same thing in the dashboard (Settings), then tell whoever maintains the file |
| Dashboards show errors on every page | `API_BASE_URL` wrong (must be the Render URL, `https://`, no trailing slash) -- fix it, then redeploy on Vercel |
| Admin login fails | `SUPERADMIN_EMAIL`/`SUPERADMIN_PASSWORD` on Render differ from what you typed |

## Rollback

- **Backend**: Render → service → Events/Deploys → pick the last good deploy
  → **Rollback**.
- **Frontends**: Vercel → Deployments → last good one → **Promote to
  Production** (or "Instant Rollback").
- Migrations are never rolled back automatically. Write them to be backwards
  compatible (add columns/tables first, remove old ones in a later release).

---

## Production (later)

When you're ready to serve real customers from `main`:

1. A **new** Supabase project (Pro plan, for backups), `vector` extension
   enabled. Use its transaction pooler (`:6543`) URL as `DATABASE_URL` and its
   session pooler (`:5432`) URL as `MIGRATION_DATABASE_URL`.
2. A second Render service on branch `main`, on a **paid** instance type (no
   sleeping). Instead of `RUN_MIGRATIONS_ON_START`, set the **Pre-Deploy
   Command** to `alembic upgrade head` (paid plans have it; migrations then
   run once before traffic switches, not on every start).
3. Variables as for dev, but `ENVIRONMENT=production` (the app then also
   requires `EMAIL_BACKEND=smtp` plus `SMTP_HOST`/`SMTP_PORT`/
   `SMTP_USERNAME`/`SMTP_PASSWORD`/`SMTP_FROM`), a new `JWT_SECRET`, and
   `SENTRY_DSN` (see operations.md).
4. Two more Vercel projects (or the same ones with production on `main`),
   `API_BASE_URL` pointing at the production backend. **Don't set
   `BOT_API_SECRET` in production** -- `/widget-test` is public.
5. Release by merging `dev` → `main`.
