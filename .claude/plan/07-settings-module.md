# Phase 7 — Settings Module (Bot Config, Branding, Toggles, Keys)

## Goal

The single place clients configure bot identity, conversation behavior,
branding, feature toggles, and deployment credentials — replacing the
hardcoded defaults Phase 4 used as stand-ins.

## Prerequisites

Phase 0 (tenancy), Phase 4 (engine reads these values at runtime).

## Data model

### `tenant_settings` (one row per tenant)
| Column | Type | Notes |
|---|---|---|
| tenant_id | UUID pk/fk | |
| bot_name | text | |
| persona_tone | enum(`formal`,`friendly`,`casual`) | |
| avatar_url | text nullable | |
| welcome_message | text | |
| starter_questions | jsonb | array of strings |
| fallback_message | text | |
| theme_color | text | hex |
| widget_position | enum(`bottom_right`,`bottom_left`) | |
| bot_enabled | bool | human-takeover master switch — client can silence the bot entirely |
| documents_enabled | bool | |
| catalog_enabled | bool | |
| leads_enabled | bool | |
| updated_at | timestamptz | |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET/PUT | `/tenant/settings` | Full settings object |
| POST | `/tenant/api-keys` | Issue a new widget site key or API secret key |
| GET | `/tenant/api-keys` | List (masked) |
| DELETE | `/tenant/api-keys/{id}` | Revoke |
| POST | `/tenant/channel-connections` | Start a channel OAuth connect flow (Phase 10 dependency, stub endpoint here) |

## How Phase 4 consumes this

Replace the hardcoded defaults in the bot engine with a lookup of
`tenant_settings` at the start of each `/bot/message` request (short in-memory
cache per tenant, e.g. 30–60s TTL, invalidated on settings update, to avoid a
DB round trip on every message):

- `bot_enabled = false` → return no reply at all (channel adapter sends nothing)
- `documents_enabled/catalog_enabled/leads_enabled = false` → that intent
  branch is removed from the router entirely, falling back instead

## Where to implement

| File | Contents |
|---|---|
| `src/app/models/settings.py` | `TenantSettings(Base, TimestampMixin)` — note: use `tenant_id` itself as the primary key/FK (one-to-one with `tenants`), **not** `TenantScopedMixin`, since that mixin gives a separate generated `id` plus `tenant_id`, which you don't want for a strictly one-row-per-tenant table |
| `src/app/models/__init__.py` | Import `TenantSettings` |
| `src/app/schemas/settings.py` | `TenantSettingsRead/Update`, `ApiKeyCreate/Read` (the read schema masks the secret — only the create response includes the raw value, once) |
| `src/app/repos/settings.py` | `get_settings(session, tenant_id)`, `update_settings(session, tenant_id, **fields)`, `create_api_key(session, tenant_id, key_type, allowed_domains=None)`, `list_api_keys(session, tenant_id)`, `revoke_api_key(session, tenant_id, key_id)` |
| `src/app/services/settings_cache.py` | A small in-process TTL cache (e.g. 30–60s) around `get_settings`, keyed by `tenant_id`, invalidated on `update_settings` — avoids a DB round trip on every `/bot/message` call |
| `src/app/api/tenant/settings.py` | `APIRouter(prefix="/tenant/settings")`: GET/PUT settings; `APIRouter(prefix="/tenant/api-keys")`: POST/GET/DELETE |
| `src/app/services/bot_engine.py` | **Edit from Phase 4**: replace the hardcoded persona/toggle defaults with calls through `services/settings_cache.py`; add the `bot_enabled`/module-toggle checks at the top of `handle_message` |

## Task checklist

1. `models/settings.py` + migration, seeded with defaults inside `services/onboarding.py`'s `onboard_tenant` (Phase 0)
2. `repos/settings.py`, `services/settings_cache.py`
3. `api/tenant/settings.py` (settings + API keys), wired into `main.py`
4. Go back to `services/bot_engine.py` (Phase 4) and swap hardcoded defaults for real settings + toggle enforcement
5. Go back to `core/deps.py`/`services/bot_engine.py` and confirm the Phase 1 tenant-suspended check and this phase's `bot_enabled` check live at the same top-of-pipeline spot

## Test plan

- Update settings → next `/bot/message` call reflects new fallback message/persona within the cache TTL
- Toggle `catalog_enabled=false` → purchase/pricing branch unreachable, confirmed via a Phase-4-style scripted conversation
- `bot_enabled=false` → `/bot/message` returns empty/no-op response
- Issue an API key → raw secret returned once; subsequent GET only shows the prefix
- Revoked key rejected on next use

## Out of scope

- Per-agent/multi-user permission settings
- A/B testing different bot configs
