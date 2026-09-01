# Phase 1 — Superuser API (Tenant Onboarding & Management)

## Goal

Give the Superuser UI everything it needs to onboard and manage tenants.

## Prerequisites

Phase 0 (tenancy schema, auth, invite/activation flow).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/superadmin/tenants` | Create tenant + owner `tenant_user` (`invited`) + send invite |
| GET | `/superadmin/tenants` | List tenants, paginated, filter by `status`, search by name |
| GET | `/superadmin/tenants/{id}` | Tenant detail incl. owner user + status |
| PATCH | `/superadmin/tenants/{id}` | Update business details, change status |
| POST | `/superadmin/tenants/{id}/resend-invite` | Invalidate old token, issue + send a new one |
| POST | `/superadmin/tenants/{id}/suspend` | Sets `tenants.status = suspended` — blocks all tenant logins and bot traffic for that tenant |
| POST | `/superadmin/tenants/{id}/reactivate` | Reverses suspend |

### `POST /superadmin/tenants` request shape

```json
{
  "name": "Acme Cafe",
  "slug": "acme-cafe",
  "owner_email": "owner@acmecafe.com"
}
```

Response includes the created tenant + owner user (no password/token in the
response — those only go out via email).

## Email sending

Introduce the real `EmailSender` implementation here (interface defined in
Phase 0): SMTP or a transactional provider (e.g. Postmark/SES). For local dev,
keep the console/log sender behind a config flag (`EMAIL_BACKEND=console`).

Email template: dashboard URL + activation link containing the raw invite
token as a query param, expiry notice.

## Suspend semantics

When a tenant is `suspended`:
- `/auth/tenant/login` returns 403 for that tenant's users
- `/bot/message` for that tenant returns a fixed "service unavailable" style
  response (checked at the very top of the bot request pipeline before any
  RAG/catalog work, to avoid wasted LLM calls)

## Task checklist

1. Tenant CRUD endpoints + Pydantic schemas
2. Wire real `EmailSender` (console backend for dev, SMTP/provider for staging+)
3. Suspend/reactivate logic + the two enforcement points above
4. Pagination/filtering/search on the list endpoint

## Test plan

- Full onboarding round-trip via API (create → invite → activate → login), email captured via test double
- Resend invite invalidates the previous token (old token now fails activation)
- Suspend blocks tenant login with 403; reactivate restores access
- List endpoint pagination/filter/search correctness

## Out of scope

- Platform admin analytics/usage dashboards
- Billing/plan tiers
- Multi-user superuser accounts/roles (single flat `platform_admins` table is enough for MVP)
