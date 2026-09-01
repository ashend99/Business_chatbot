# Phase 0 — Foundation: Tenancy, Auth, Onboarding

## Goal

Stand up the shared tenancy/identity layer every other module depends on:
tenants (which double as the single login/owner account per the merged-model
decision below), API keys, channel connections, JWT auth, and the invite-based
onboarding/activation flow.

> **Design decision (supersedes the original split-table draft):** `Tenant`
> holds the login credentials directly (`email`, `activation_password_hash`)
> instead of a separate `TenantUser` table — one login per tenant business for
> MVP, no multi-staff accounts. There's also no `PlatformAdmin` table;
> superuser login is checked against a single credential pair from
> environment config (see JWT claims below). Trade-off: adding multiple staff
> logins per tenant later requires introducing a real `TenantUser` table and
> migrating `email`/`activation_password_hash` off `Tenant` — acceptable for
> MVP speed, revisit if/when a client asks for multiple staff logins.

## Prerequisites

None — this is the starting point.

## Suggested project layout

```
src/app/
  core/           # settings, security (jwt, hashing), config
  db/             # engine/session, base model
  models/         # SQLAlchemy ORM models
  schemas/        # Pydantic request/response models
  api/
    superadmin/
    tenant/
    bot/
    auth/
  services/       # business logic (email sending, token issuance, etc.)
  repositories/   # tenant-scoped query helpers (see below)
alembic/
tests/
```

## Data model

### `tenants` (as coded in `src/app/models/tenants.py`)
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| name | text | business display name |
| slug | text unique | used in URLs/future subdomains |
| is_active | bool | default `true` — doubles as the suspend/reactivate flag (Phase 1) |
| email | text, unique, nullable | login email — **globally unique**, since login is by email alone with no tenant/slug field |
| contact_person / contact_number / address | text, nullable | business details collected at onboarding |
| activation_password_hash | text, nullable | null until the tenant activates via invite token; presence of a hash is what distinguishes "invited" from "active" (no separate `status` enum) |
| created_at / updated_at | timestamptz | |

### `invite_tokens`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk → tenants | |
| token_hash | text, unique | sha256 of the raw token — never store the raw token |
| expires_at | timestamptz | now + 72h |
| is_used | bool | default `false` |
| used_at | timestamptz, nullable | |
| created_at / updated_at | timestamptz | |

### `tenant_api_keys` (not yet coded — add to `tenants.py` in this phase)
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk → tenants | |
| key_prefix | text | short, shown in dashboard for identification |
| hashed_secret | text | sha256 or bcrypt of the full key |
| allowed_domains | text[] | for widget key type |
| key_type | enum(`widget_site_key`,`api_secret`) | |
| revoked_at | timestamptz, nullable | |
| created_at | timestamptz | |

### `channel_connections` (as coded in `src/app/models/tenants.py`)
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk → tenants | |
| channel_type | enum(`facebook`,`twitter`,`instagram`) | real column, not buried in JSON — required for the unique constraint and the tenant-resolution lookup below |
| external_account_id | text, indexed | e.g. Facebook Page ID — used to resolve tenant on inbound webhook |
| account_name | text, nullable | display name shown in the dashboard |
| encrypted_access_token | text | Fernet-encrypted at rest (see Phase 11 for key management) |
| status | enum(`active`,`inactive`) | single source of truth for connection state — no separate boolean flag |
| created_at / updated_at | timestamptz | |

`UniqueConstraint("channel_type", "external_account_id")` — one connection per
external account platform-wide.

## Auth design

### JWT claims
- Superuser token: `{sub: "superadmin", scope: "platform_admin"}` — checked
  against a single credential pair from environment config
  (`SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD_HASH` in `core/config.py`), no DB
  table. Revisit with a real `platform_admins` table if more than one platform
  operator ever needs a login.
- Tenant token: `{sub: tenant_id, scope: "tenant"}` — `Tenant.id` doubles as
  the account identity since there's no separate `TenantUser` row.
- Both short-lived access tokens (e.g. 30–60 min) — add refresh tokens only if
  needed later; not required for MVP usability at this scale.

### Endpoints (this phase)

| Method | Path | Purpose |
|---|---|---|
| POST | `/superadmin/auth/login` | checked against env-configured credentials |
| POST | `/auth/tenant/login` | tenant login by `email` + `activation_password_hash` |
| POST | `/auth/activate` | `{token, new_password}` → sets `activation_password_hash`, marks token used |
| POST | `/auth/request-password-reset` | (minimal) issues a reset token via the same `invite_tokens` mechanism |
| POST | `/auth/reset-password` | `{token, new_password}` |

### Onboarding flow (detailed)

1. Superuser calls `POST /superadmin/tenants` with business details + contact
   email (full endpoint spec lives in Phase 1).
2. Backend creates a `tenants` row (`is_active=true`,
   `activation_password_hash=null`) — no separate user row.
3. Backend generates a random 32-byte URL-safe token, stores only its SHA-256
   hash + `expires_at` (now + 72h) in `invite_tokens`, and sends (or logs,
   until Phase 1's email service is wired) an email containing the dashboard
   URL + raw token.
4. Tenant visits `/activate?token=...` in the dashboard → calls
   `POST /auth/activate` → backend hashes the incoming token, looks it up,
   checks `expires_at` and `is_used == false`, sets
   `tenants.activation_password_hash`, marks the token `is_used=true`,
   `used_at=now()`.
5. Tenant now logs in normally via `POST /auth/tenant/login`.

### Tenant-scoping enforcement pattern

Every tenant-scoped repository function requires `tenant_id` as its first
argument — no function may query a tenant-scoped table without it. Example
shape (not final code, just the contract):

```python
async def get_document(session, tenant_id: UUID, document_id: UUID) -> Document | None:
    stmt = select(Document).where(
        Document.id == document_id,
        Document.tenant_id == tenant_id,
    )
    ...
```

A FastAPI dependency (`get_current_tenant_id`) decodes the JWT and yields
`tenant_id` — route handlers never accept `tenant_id` from the request body,
query params, or path.

### Password/token security notes

- bcrypt cost factor 12 (passlib default is fine, confirm explicitly in config)
- Invite/reset tokens: 32 bytes from `secrets.token_urlsafe`, stored hashed,
  72h expiry (invite) / 1h expiry (password reset)
- Rate-limit login and activation endpoints (defer implementation detail to
  Phase 11, but keep the endpoints structured so a rate limiter can wrap them)

## Where to implement

| File | Contents |
|---|---|
| `src/app/core/config.py` | `Settings(BaseSettings)`: `database_url`, `jwt_secret`, `jwt_algorithm="HS256"`, `access_token_expire_minutes`, `bcrypt_rounds`, `openai_api_key`, `email_backend`, `superadmin_email`, `superadmin_password_hash` |
| `src/app/core/security.py` | `hash_password`, `verify_password` (passlib `CryptContext(schemes=["bcrypt"])`), `create_access_token(claims, expires_minutes)`, `decode_access_token(token)`, `generate_raw_token()` (`secrets.token_urlsafe(32)`), `hash_token(raw)` (sha256 hexdigest) |
| `src/app/db/session.py` | `engine = create_async_engine(settings.database_url)`, `AsyncSessionLocal = async_sessionmaker(engine)`, `async def get_db_session()` yielding a session |
| `src/app/models/tenants.py` | **Already coded**: `Tenant`, `InviteTokens`, `ChannelConnections` (+ `ChannelTypes`/`ChannelStatuses` enums). Still to add: `TenantApiKey(Base, TimestampMixin)` for the table above |
| `src/app/models/__init__.py` | Import every class from `tenants.py` (currently empty — this is blocking Alembic autogenerate right now) |
| `src/app/schemas/tenants.py` | `TenantCreate`, `TenantRead`, `LoginRequest`, `TokenResponse`, `ActivateRequest`, `PasswordResetRequest` |
| `src/app/repos/tenants.py` | `get_tenant_by_id(session, tenant_id)`, `get_tenant_by_email(session, email)`, `create_tenant(session, name, slug, email, contact_person, contact_number, address)`, `create_invite_token(session, tenant_id)`, `get_invite_token_by_hash(session, token_hash)`, `mark_invite_used(session, invite_token_id)` |
| `src/app/services/email.py` | `class EmailSender(Protocol): def send(self, to, subject, body) -> None`, `class ConsoleEmailSender` (logs instead of sending) |
| `src/app/services/onboarding.py` | `async def onboard_tenant(session, email_sender, name, slug, contact_email, ...) -> Tenant` (creates tenant + invite token + sends email), `async def activate_tenant(session, raw_token, new_password) -> Tenant` |
| `src/app/core/deps.py` | `get_current_platform_admin` (checks the bearer token's `scope` claim against env-configured superadmin credentials, no DB lookup), `get_current_tenant_id` (decodes JWT, confirms `tenants.is_active == true` via `repos.tenants.get_tenant_by_id`) |
| `src/app/api/auth/router.py` | `APIRouter(prefix="/auth")`: `POST /tenant/login`, `POST /activate`, `POST /request-password-reset`, `POST /reset-password` |
| `src/app/api/superadmin/auth.py` | `APIRouter(prefix="/superadmin/auth")`: `POST /login` — kept in its own router/module, separate from tenant auth |
| `src/app/main.py` | `app = FastAPI()`; `app.include_router(auth_router)`; `app.include_router(superadmin_auth_router)` (more routers added as later phases land) |

## Migration workflow (Alembic)

`database/alembic/` currently exists but is empty — it still needs `env.py`,
`script.py.mako`, and a `versions/` folder.

1. From the repo root: `alembic init database/alembic`
2. Create `alembic.ini` at the repo root with `script_location = database/alembic`
3. In `database/alembic/env.py`: `from app.db.base import Base`, `import app.models  # noqa: F401 — populates Base.metadata`, set `target_metadata = Base.metadata`; read the DB URL from `app.core.config.settings.database_url` instead of the `alembic.ini` placeholder
4. `alembic revision --autogenerate -m "phase 0 foundation"`
5. Manually add `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` to the generated migration — autogenerate does not create Postgres extensions
6. Review the generated migration, then `alembic upgrade head`

## Tasks checklist

1. `core/config.py`, `core/security.py`, `db/session.py`
2. Add `TenantApiKey` to `models/tenants.py`; fill in `models/__init__.py`
3. `alembic init` + `env.py` wiring + first migration (steps above)
4. `schemas/tenants.py`, `repos/tenants.py`
5. `services/email.py`, `services/onboarding.py`
6. `core/deps.py`
7. `api/auth/router.py`, `api/superadmin/auth.py`, wire both into `main.py`
8. Seed script (`scripts/seed_dev.py` at repo root, run via `python scripts/seed_dev.py`) — one demo tenant (activated, with a known password) for local dev/testing

## Test plan

- Unit: password hash/verify round-trip; JWT encode/decode; invite token hash
  lookup; expired token rejected; used token rejected
- Integration (pytest + httpx against a test DB):
  - Create tenant → invite issued → activate with correct token → login succeeds
  - Activate with expired token → 400
  - Activate with already-used token → 400
  - Tenant login before activation → 401
  - Cross-tenant: JWT for tenant A cannot be used to fetch tenant B's data (add a placeholder protected route in this phase's tests to prove the dependency works)

## Out of scope (this phase)

- Multiple staff users per tenant (schema allows it, not exposed)
- Real transactional email provider (stub/log only)
- MFA
