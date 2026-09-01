# Phase 12 — Deployment

## Goal

Ship the platform to a staging environment first, then production.

## Prerequisites

All prior phases; Phase 11 hardening pass complete before production traffic.

## Components

| Component | Where | Notes |
|---|---|---|
| FastAPI backend | Containerized (Dockerfile), deployed to a host that supports long-running containers (e.g. Fly.io/Railway/Render/a small VM) | Vercel is not suitable for the backend (needs persistent DB connections, background-ish work for embedding batches) |
| Postgres + pgvector | Managed Postgres with pgvector support (e.g. Neon, Supabase, RDS with the extension enabled) | Confirm pgvector extension available before committing to a provider |
| n8n | Self-hosted container, same network as the backend or reachable via authenticated HTTPS | Keep customer message content off third-party SaaS (n8n cloud) per the earlier data-handling note |
| Superuser UI + Client Dashboard | Vercel (Next.js) | Two separate Vercel projects or one multi-tenant Next.js app with route-based separation — either works, pick based on how much UI is actually shared |

## Environment/secrets

- Per-environment `.env` (local/staging/prod) — never committed; align with
  `sourceme.sh`'s existing loading convention already in the repo
- Secrets (DB URL, OpenAI key, JWT signing key, Fernet key, Meta app
  secret) injected via the hosting platform's secret store, not baked into
  the image

## CI/CD

- On push: lint (`ruff`), type-check (`mypy`), test (`pytest`)
- On merge to main: build + push image, run Alembic migrations against the
  target DB, deploy
- Migrations run as an explicit pre-deploy step, not on app startup, so a
  failed migration blocks the deploy rather than half-starting the app

## Where to implement

| File | Contents |
|---|---|
| `Dockerfile` (repo root) | Multi-stage build: install via `uv sync --frozen`, run `alembic upgrade head` as a separate deploy step (not in the image's `CMD`), then `uvicorn app.main:app` |
| `.dockerignore` (repo root) | Exclude `.venv/`, `dashboard/`, `.git/`, `tests/` from the backend image |
| `.github/workflows/ci.yml` | lint (`ruff`) → type-check (`mypy`) → test (`pytest`) → (on main) build/push image → run migrations → deploy |
| `docker-compose.yml` (repo root, local dev only) | Postgres+pgvector image, n8n image, backend — for local end-to-end testing of Phase 10's workflow without hitting real cloud infra |
| `dashboard/vercel.json` / Vercel project settings | Env vars pointed at the staging/production backend URL |

## Task checklist

1. `Dockerfile` + `.dockerignore` for the backend
2. Provision managed Postgres (pgvector enabled), run Phase 0's baseline
   migration
3. Self-host n8n container, import the Phase 10 workflow
4. Vercel projects for both frontends, env vars pointed at the staging
   backend URL
5. CI pipeline (lint/type-check/test/build/migrate/deploy)

## Test plan (staging smoke test)

- Superuser UI: onboard a real test tenant end-to-end (invite email actually
  arrives)
- Client Dashboard: log in, upload+publish a document, add a catalog item,
  view a lead
- Widget: embed on a real test page, full conversation incl. lead capture
- n8n: connect a Meta test Page, send a message, verify reply round-trip
- Confirm RLS policies and rate limits (Phase 11) are active in staging, not
  just local dev

## Out of scope

- Multi-region deployment
- Blue/green or canary deploy strategies (a single staged rollout is enough
  at this scale)
- Autoscaling policy tuning beyond the hosting provider's defaults
