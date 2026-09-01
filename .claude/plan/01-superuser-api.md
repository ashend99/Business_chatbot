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

## Where to implement

| File | Contents |
|---|---|
| `src/app/schemas/tenants.py` | Add `TenantUpdate`, `TenantListItem`, `TenantDetail` (extends Phase 0's schemas) |
| `src/app/repos/tenants.py` | Add `list_tenants(session, status=None, search=None, page, page_size)`, `update_tenant(session, tenant_id, **fields)`, `set_tenant_status(session, tenant_id, status)`, `invalidate_pending_invites(session, tenant_user_id)` |
| `src/app/services/onboarding.py` | Add `resend_invite(session, email_sender, tenant_id)` — calls `invalidate_pending_invites` then re-runs the invite-creation half of `onboard_tenant` |
| `src/app/services/email.py` | Add the real provider implementation (e.g. `SmtpEmailSender` or a provider SDK wrapper), selected in `core/config.py` via `email_backend` |
| `src/app/api/superadmin/tenants.py` | `APIRouter(prefix="/superadmin/tenants")`: the 6 endpoints below — all behind `get_current_platform_admin` |
| `src/app/main.py` | `app.include_router(superadmin_tenants_router)` |

Suspend enforcement touches two other phases' code once they exist:
`core/deps.py`'s `get_current_tenant_user` (Phase 0) and `services/bot_engine.py`'s
top-of-pipeline check (Phase 4) both need to read `tenants.status`.

## Task checklist

1. `repos/tenants.py`: list/update/suspend/reactivate/resend-invite query functions
2. `services/email.py`: real `EmailSender` implementation (console stays as the dev/test default)
3. `api/superadmin/tenants.py`: the 6 endpoints, wired into `main.py`
4. Confirm suspend is actually checked in `core/deps.py` (Phase 0 code) and note the same check needs adding to `services/bot_engine.py` once Phase 4 exists

## Test plan

- Full onboarding round-trip via API (create → invite → activate → login), email captured via test double
- Resend invite invalidates the previous token (old token now fails activation)
- Suspend blocks tenant login with 403; reactivate restores access
- List endpoint pagination/filter/search correctness

## Out of scope

- Platform admin analytics/usage dashboards
- Billing/plan tiers
- Multi-user superuser accounts/roles (single flat `platform_admins` table is enough for MVP)
