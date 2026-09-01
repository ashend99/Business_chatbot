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

## Where to implement

| File | Contents |
|---|---|
| `src/app/schemas/widget.py` | `WidgetSessionRequest` (`site_key`), `WidgetSessionResponse` (`session_token`, `conversation_id`, plus the branding fields read alongside it) |
| `src/app/core/deps.py` | Add `get_current_widget_session` — decodes the widget session JWT (distinct claim shape: `{tenant_id, conversation_id, scope: "widget_session"}`), and rejects if the request's `conversation_id` (path/body) doesn't match the token's — this is what keeps a stolen token scoped to one conversation |
| `src/app/repos/settings.py` | Add `get_api_key_by_prefix_or_lookup(session, site_key)` — validates key + `allowed_domains` against the request's `Origin` header |
| `src/app/api/widget/router.py` | `APIRouter(prefix="/widget")`: `POST /session` — validates site key + origin, creates a `Conversation` (via Phase 4's `repos/conversations.py`), issues the session JWT |
| `src/app/api/bot/router.py` | **Small edit from Phase 4**: accept either the service API-key dependency (n8n) or `get_current_widget_session` on `POST /message`, resolving `tenant_id`/`conversation_id` from whichever succeeded |
| `widget/` (new top-level folder, separate small build) | Vanilla TS/JS bundle: chat bubble UI, calls `/widget/session` then `/bot/message`, persists `session_token` in `localStorage` |

## Task checklist

1. `api/widget/router.py` (`/widget/session`), wired into `main.py`
2. `core/deps.py`'s `get_current_widget_session`
3. Edit `api/bot/router.py` to accept both auth paths
4. `widget/` JS bundle (bubble UI, session persistence, message send/receive)
5. Branding fetch (Phase 7's settings) wired into the widget's initial load

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
