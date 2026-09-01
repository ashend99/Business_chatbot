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

## Task checklist

1. Model + migration, seeded with sensible defaults on tenant creation
2. Settings GET/PUT endpoint
3. API key issuance/list/revoke endpoints (raw secret shown once at creation only, never again)
4. Wire Phase 4's engine to read real settings instead of hardcoded defaults
5. Wire Phase 1's suspend logic and this phase's `bot_enabled` to share the same enforcement point in the bot pipeline

## Test plan

- Update settings → next `/bot/message` call reflects new fallback message/persona within the cache TTL
- Toggle `catalog_enabled=false` → purchase/pricing branch unreachable, confirmed via a Phase-4-style scripted conversation
- `bot_enabled=false` → `/bot/message` returns empty/no-op response
- Issue an API key → raw secret returned once; subsequent GET only shows the prefix
- Revoked key rejected on next use

## Out of scope

- Per-agent/multi-user permission settings
- A/B testing different bot configs
