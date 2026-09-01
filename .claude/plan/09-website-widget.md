# Phase 9 — Website Widget

## Goal

Embeddable chat widget: `<script>` snippet, domain-restricted site key,
short-lived session tokens, calling the same `/bot/message` engine from
Phase 4.

## Prerequisites

Phase 4 (bot engine), Phase 7 (site keys + branding settings).

## Flow

1. Client copies a snippet into their site:
   ```html
   <script src="https://cdn.yourplatform.com/widget.js" data-site-key="pk_live_..."></script>
   ```
2. On page load, the widget script calls `POST /widget/session` with the site
   key.
3. Backend validates:
   - Key exists, not revoked, `key_type = widget_site_key`
   - The request's `Origin`/`Referer` header matches an entry in
     `allowed_domains` for that key
4. Backend creates a new `conversations` row (`channel_type=website_widget`,
   a generated `external_user_id` such as a random visitor id) and returns a
   short-lived session JWT scoped to `{tenant_id, conversation_id}`.
5. Widget stores the session token (e.g. `localStorage`, scoped to that
   domain) and uses it as the bearer token for subsequent
   `POST /bot/message` calls — no need to re-send/re-validate the site key
   per message.
6. Session token expires (e.g. 24h); widget silently calls
   `/widget/session` again to start a fresh conversation if it's gone.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/widget/session` | `{site_key}` (+ Origin header) → `{session_token, conversation_id}` |
| POST | `/bot/message` | Same endpoint as Phase 4, but accepts the widget session token as an alternate auth method scoped to exactly one `conversation_id` (can't be reused for a different conversation, unlike the n8n service-to-service key) |

## Widget UI

- Minimal chat bubble + expandable panel (iframe or shadow DOM to avoid CSS
  collisions with the host page)
- Reads branding from `tenant_settings` (theme color, position, avatar,
  welcome message, starter questions) — fetch these along with the session
  response to avoid a second round trip
- Renders `actions` from the bot response if useful (e.g. a "we've got your
  info" confirmation state), but the underlying widget UI doesn't need
  special-casing beyond showing the assistant's `reply` text

## Task checklist

1. `/widget/session` endpoint (site key validation, origin check, session token issuance)
2. Session-token auth path on `/bot/message` (distinct from the n8n service credential — scoped to one conversation, can't address others)
3. Widget JS bundle (bubble UI, session persistence, message send/receive)
4. Branding fetch wired into the widget's initial load

## Test plan

- Static HTML test page with the snippet against a seeded tenant → full
  conversation round-trip, including a lead-capture flow ending in
  `lead_created`
- Request from a non-allowed origin → `/widget/session` rejected
- Expired session token → widget transparently starts a new session (new
  `conversation_id`), doesn't crash
- Session token for tenant A rejected if used to call `/bot/message` with a
  `conversation_id` belonging to tenant B (defense-in-depth check even though
  the token is scoped)

## Out of scope

- Deep theming beyond color/position/avatar
- Native mobile SDKs
- Multi-language UI strings (defer if a client needs it)
