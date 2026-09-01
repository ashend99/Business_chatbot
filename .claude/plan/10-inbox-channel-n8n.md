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

## Task checklist

1. OAuth connect flow + callback endpoint, `channel_connections` writes
2. Internal "resolve tenant by external_account_id" endpoint for n8n to call
3. n8n workflow: webhook → signature verify → tenant resolve → `/bot/message` → conditional send
4. Token encryption at rest (Fernet key management — see Phase 11)

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
