# Phase 0 — Foundation: Tenancy, Auth, Onboarding

## Goal

Stand up the shared tenancy/identity layer every other module depends on:
tenants, platform admins, tenant users, API keys, channel connections, JWT
auth, and the invite-based onboarding/activation flow.

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

### `tenants`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| name | text | business display name |
| slug | text unique | used in URLs/future subdomains |
| status | enum(`active`,`suspended`) | default `active` |
| created_at / updated_at | timestamptz | |

### `platform_admins`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| email | text unique | |
| hashed_password | text | bcrypt |
| created_at | timestamptz | |

Kept entirely separate from `tenant_users` — no shared table with a role flag,
so a bug can't accidentally elevate a tenant user to platform-admin scope.

### `tenant_users`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk → tenants | |
| email | text | **globally unique** (see note below) |
| hashed_password | text nullable | null until activation |
| role | enum(`owner`) | single value for MVP; enum leaves room to add roles later |
| status | enum(`invited`,`active`,`suspended`) | default `invited` |
| must_reset_password | bool | true until first password set |
| created_at / updated_at | timestamptz | |

> **Correction from the original draft:** `tenant_users.email` must be
> globally unique, not unique-per-tenant. The tenant login form only asks for
> email + password (no tenant/slug field), so the backend has to resolve
> `tenant_id` from the email alone. A per-tenant unique constraint would allow
> two different tenants to register the same email and make login ambiguous.

### `invite_tokens`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_user_id | UUID fk → tenant_users | |
| token_hash | text | sha256 of the raw token — never store raw token |
| expires_at | timestamptz | now + 72h |
| used_at | timestamptz nullable | |
| created_at | timestamptz | |

### `tenant_api_keys`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk → tenants | |
| key_prefix | text | short, shown in dashboard for identification |
| hashed_secret | text | sha256 or bcrypt of the full key |
| allowed_domains | text[] | for widget key type |
| key_type | enum(`widget_site_key`,`api_secret`) | |
| revoked_at | timestamptz nullable | |
| created_at | timestamptz | |

### `channel_connections`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk → tenants | |
| channel_type | enum(`facebook`,`instagram`,`whatsapp`,`website_widget`) | |
| external_account_id | text | e.g. Facebook Page ID — indexed, used to resolve tenant on inbound webhook |
| encrypted_access_token | text | Fernet-encrypted at rest (see Phase 11 for key management) |
| status | enum(`active`,`disconnected`) | |
| created_at | timestamptz | |

Unique index on `(channel_type, external_account_id)` — one connection per
external account platform-wide.

## Auth design

### JWT claims
- Superuser token: `{sub: platform_admin_id, scope: "platform_admin"}`
- Tenant user token: `{sub: tenant_user_id, tenant_id, scope: "tenant_user", role}`
- Both short-lived access tokens (e.g. 30–60 min) — add refresh tokens only if
  needed later; not required for MVP usability at this scale.

### Endpoints (this phase)

| Method | Path | Purpose |
|---|---|---|
| POST | `/superadmin/auth/login` | platform admin login |
| POST | `/auth/tenant/login` | tenant user login |
| POST | `/auth/activate` | `{token, new_password}` → sets password, activates account |
| POST | `/auth/request-password-reset` | (minimal) issues a reset token via the same `invite_tokens`-style mechanism |
| POST | `/auth/reset-password` | `{token, new_password}` |

### Onboarding flow (detailed)

1. Superuser calls `POST /superadmin/tenants` with business details + contact
   email (full endpoint spec lives in Phase 1).
2. Backend creates `tenants` row + `tenant_users` row (`status=invited`,
   `hashed_password=null`).
3. Backend generates a random 32-byte URL-safe token, stores only its SHA-256
   hash in `invite_tokens`, and sends (or logs, until Phase 1's email service
   is wired) an email containing the dashboard URL + raw token.
4. Tenant visits `/activate?token=...` in the dashboard → calls
   `POST /auth/activate` → backend hashes the incoming token, looks it up,
   checks `expires_at` and `used_at IS NULL`, sets `hashed_password`,
   `status=active`, `must_reset_password=false`, marks token `used_at=now()`.
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
| `src/app/core/config.py` | `Settings(BaseSettings)`: `database_url`, `jwt_secret`, `jwt_algorithm="HS256"`, `access_token_expire_minutes`, `bcrypt_rounds`, `openai_api_key`, `email_backend` |
| `src/app/core/security.py` | `hash_password`, `verify_password` (passlib `CryptContext(schemes=["bcrypt"])`), `create_access_token(claims, expires_minutes)`, `decode_access_token(token)`, `generate_raw_token()` (`secrets.token_urlsafe(32)`), `hash_token(raw)` (sha256 hexdigest) |
| `src/app/db/session.py` | `engine = create_async_engine(settings.database_url)`, `AsyncSessionLocal = async_sessionmaker(engine)`, `async def get_db_session()` yielding a session |
| `src/app/models/tenants.py` | `Tenant(Base, TimestampMixin)`, `PlatformAdmin(Base, TimestampMixin)`, `TenantUser(Base, TenantScopedMixin)`, `InviteToken(Base, TimestampMixin)`, `TenantApiKey(Base, TenantScopedMixin)`, `ChannelConnection(Base, TenantScopedMixin)` — all in one file since they're identity-adjacent; split later only if the file gets unwieldy |
| `src/app/models/__init__.py` | Import every class from `tenants.py` (and later phases' modules) so `Base.metadata` is populated |
| `src/app/schemas/tenants.py` | `TenantCreate`, `TenantRead`, `TenantUserRead`, `LoginRequest`, `TokenResponse`, `ActivateRequest`, `PasswordResetRequest` |
| `src/app/repos/tenants.py` | `get_tenant_by_id(session, tenant_id)`, `get_tenant_user_by_email(session, email)` (global, per the correction above), `create_tenant_with_owner(session, name, slug, owner_email)`, `create_invite_token(session, tenant_user_id)`, `get_invite_token_by_hash(session, token_hash)`, `mark_invite_used(session, invite_token_id)` |
| `src/app/services/email.py` | `class EmailSender(Protocol): def send(self, to, subject, body) -> None`, `class ConsoleEmailSender` (logs instead of sending) |
| `src/app/services/onboarding.py` | `async def onboard_tenant(session, email_sender, name, slug, owner_email) -> Tenant` (creates tenant + invited owner + invite token + sends email), `async def activate_tenant_user(session, raw_token, new_password) -> TenantUser` |
| `src/app/core/deps.py` | `get_current_platform_admin`, `get_current_tenant_user`, `get_current_tenant_id` — decode JWT via `security.decode_access_token`, check `scope` claim, and for tenant users confirm `tenants.status == active` (query via `repos.tenants.get_tenant_by_id`) before allowing the request through |
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
2. `models/tenants.py` + `models/__init__.py` update
3. `alembic init` + `env.py` wiring + first migration (steps above)
4. `schemas/tenants.py`, `repos/tenants.py`
5. `services/email.py`, `services/onboarding.py`
6. `core/deps.py`
7. `api/auth/router.py`, `api/superadmin/auth.py`, wire both into `main.py`
8. Seed script (`scripts/seed_dev.py` at repo root, run via `python scripts/seed_dev.py`) — one platform admin, one demo tenant, for local dev/testing

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
