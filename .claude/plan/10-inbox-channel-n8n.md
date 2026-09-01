# Phase 10 — Inbox Channel Integration via n8n

## Goal

Connect Facebook/Instagram business inboxes (WhatsApp as a documented
follow-on) to the same `/bot/message` engine, using self-hosted n8n as the
channel adapter so per-platform webhook/send-API code doesn't need to be
hand-rolled in the core backend.

## Prerequisites

Phase 4 (bot engine), Phase 7 (`bot_enabled` toggle + `channel_connections`
management endpoint stub).

## Channel connection flow (dashboard side)

1. Client clicks "Connect Facebook Page" in Settings.
2. Standard Meta OAuth redirect → client grants page permissions.
3. Backend receives the OAuth callback, stores the page's access token
   (Fernet-encrypted) and `external_account_id` (Page ID) in
   `channel_connections` (`channel_type=facebook`, `status=active`).
4. Repeat per platform (Instagram reuses the same Meta app/permissions model
   in most cases; confirm current Meta API requirements when implementing).

## n8n workflow design

One shared workflow (not one per tenant) handles all tenants for a given
channel type — tenant is resolved at runtime from the inbound payload:

1. **Webhook node** — receives Meta's inbound message event.
2. **Code node** — verify `X-Hub-Signature-256` against your Meta app secret
   (not a per-tenant secret — this validates the request came from Meta, not
   the specific tenant).
3. **Code/Function node** — extract `page_id`/`external_account_id` and the
   message text/sender PSID from the payload.
4. **HTTP Request node** — `GET` or a small internal lookup endpoint to
   resolve `tenant_id` from `channel_connections.external_account_id` (or
   just query it directly if n8n has DB access — prefer going through the
   API to keep DB credentials out of n8n).
5. **HTTP Request node** — `POST /bot/message` with
   `{tenant_id, channel_type: "facebook", external_user_id: psid, text}`,
   authenticated with an internal service credential (not the tenant's own
   API key, since n8n is trusted infra, not an external integrator).
6. **IF node** — if the response reply is empty/null (covers both
   `bot_enabled=false` and a suspended tenant), stop — no outbound send.
7. **HTTP Request node** — send the reply back via the Meta Graph API using
   that tenant's stored access token from `channel_connections`.

## Where to implement

| File | Contents |
|---|---|
| `src/app/schemas/channels.py` | `ChannelConnectRequest/Response`, `TenantResolveResponse` |
| `src/app/repos/tenants.py` | Add `get_channel_connection_by_external_id(session, channel_type, external_account_id)`, `create_channel_connection(session, tenant_id, ...)` (Fernet-encrypt the access token before insert — use `core/security.py`'s encryption helper, add one if it doesn't exist yet) |
| `src/app/api/tenant/channels.py` | `APIRouter(prefix="/tenant/channels")`: OAuth start + callback endpoints |
| `src/app/api/bot/internal.py` | A small internal-only router (still under `/bot` auth, service-credential only): `GET /internal/resolve-tenant?channel_type=...&external_account_id=...` — the one call n8n makes before calling `/bot/message` |
| `n8n/workflows/*.json` (new top-level folder) | Exported n8n workflow definitions, version-controlled alongside the code that they call |

## Task checklist

1. `repos/tenants.py` additions + `api/tenant/channels.py` OAuth connect/callback flow
2. `api/bot/internal.py` tenant-resolve endpoint
3. Build the n8n workflow (webhook → signature verify → call `/bot/internal/resolve-tenant` → call `/bot/message` → conditional send), export JSON into `n8n/workflows/`
4. Confirm token encryption (Fernet key from `core/config.py`, sourced from a secret manager — finalized in Phase 11) is actually applied before storage, not just planned

## Test plan

- Meta developer sandbox: send a test message to a connected test Page →
  verify full round-trip reply appears in the sandbox inbox
- Tampered/missing signature → webhook handler rejects with 401, no
  downstream calls made
- `bot_enabled=false` for that tenant → message is received/logged (for
  traceability) but no outbound reply sent
- Disconnect a channel → subsequent webhook events for that
  `external_account_id` are ignored (no matching `channel_connections` row,
  or `status=disconnected`)

## Out of scope (documented follow-ons)

- WhatsApp Business API (different message format/pricing model — separate
  workflow when prioritized)
- Instagram-specific DM nuances beyond Messenger platform parity
- In-dashboard unified inbox view (client continues using the native
  Facebook/Instagram inbox app directly when the bot is disabled)
