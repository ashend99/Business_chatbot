# Architecture v0.1

What this system actually is, as of this version — not a plan, a snapshot of
the real, working code. The original phase-by-phase design lives in
[.claude/plan/](.claude/plan/) and is kept as a historical record; several of
its decisions (notably Phase 4's intent router) were superseded during
implementation and are called out below where that happened. For how to run
and modify things day to day, see [AGENTS.md](AGENTS.md).

## 1. System overview

A multi-tenant AI chatbot platform for small businesses. One FastAPI backend,
one Next.js client dashboard, one Postgres database (with `pgvector` for
embeddings). Each tenant (a business) configures a knowledge base
(documents), a product/service catalog, and lead-capture fields through the
dashboard; an LLM agent then handles that business's customer conversations
— answering questions, looking up pricing/stock, capturing leads, and
building/confirming orders — across whatever channel the conversation comes
in on.

The platform makes no assumption about *what kind* of business a tenant is.
There is no `business_type`/`vertical` field anywhere in the schema —
generalization across restaurants, cake makers, online sellers, etc. comes
entirely from what a tenant puts in their own catalog/documents/lead fields,
not from branching code.

## 2. Multi-tenancy model

Shared Postgres, isolated at the application layer:

- `TenantScopedMixin` (`src/app/db/base.py`) gives every tenant-owned table
  `id` (UUID pk), `tenant_id` (FK), `created_at`, `updated_at`.
- `tenant_scope()` (`src/app/repos/tenant_scope.py`) is the single helper
  every tenant-scoped query filters through — never a bare
  `.where(Model.tenant_id == ...)`. This is the entire isolation mechanism;
  there is no Postgres RLS layer (the original plan considered it as
  defense-in-depth, not built).
- Auth is two separate JWT scopes: `tenant` (dashboard login,
  `get_current_tenant_id`) and a distinct `api_secret`-key scheme for
  service callers hitting `/bot/message` (`get_current_service_tenant`,
  `TenantApiKeys` table). A platform-admin scope exists separately for
  tenant onboarding (`superadmin` router), env-configured credentials, no
  DB table.

## 3. Backend module map (`src/app/`)

```
models/       SQLAlchemy ORM, one file per domain: tenants, documents,
              catalog, conversations, leads, orders, settings, admin
repos/        query functions, filenames mirror models/. Every function
              takes tenant_id explicitly and filters through tenant_scope()
schemas/      Pydantic request/response models, filenames mirror models/
services/     business logic: bot_engine, bot_tools, prompt_builder,
              settings_resolver, money, chunking, embeddings, publishing,
              notifications, onboarding, email
api/          FastAPI routers: auth/, superadmin/ (tenants, settings,
              api keys), tenant/ (one file per dashboard resource),
              bot/ (POST /bot/message)
core/         config (pydantic-settings), security (JWT/password hashing),
              deps (get_current_tenant_id, get_current_service_tenant, ...)
components/rag/  retrieval implementations (naive + hybrid)
```

**The bot/admin repo split is a hard boundary.** Two domains have two
parallel repo modules: `repos/leads.py` (bot-write-only — the only way the
chat pipeline writes a lead) vs. `repos/leads_admin.py` (the dashboard's
read/update surface), and identically `repos/orders.py` vs.
`repos/orders_admin.py`. The `/bot` router, `bot_engine.py`, and
`bot_tools.py` must never import an `_admin` module. This is what makes
"the bot can create leads/orders but never read existing ones, sales
figures, or settings" an enforced architectural property instead of a
convention that erodes over time.

## 4. The agent (`services/bot_engine.py` + `bot_tools.py`)

Originally planned (`.claude/plan/04-bot-core-engine.md`) as a deterministic
intent classifier dispatching into hardcoded branches plus a
`lead_flow_state` state machine. That was replaced during implementation
with a real tool-calling agent: `langgraph.prebuilt.create_react_agent`
(LangGraph ReAct agent) over a fixed toolset, with a Postgres-backed
checkpointer giving it turn-by-turn memory per conversation
(`thread_id = conversation_id`). `conversations`/`messages`
(`repos/conversations.py`) is a *separate* human-readable business record
(source of truth for the dashboard's Conversations page) — not read back
into the agent's own context.

### Tools (`bot_tools.py`), built fresh per request

`build_tools` only returns the tools this tenant's effective settings allow
(`prompt_builder.enabled_tool_names` — the same list the system prompt is
assembled from, so prompt and toolset can't disagree; see §5). The full set:

- **`search_documents`** — RAG lookup over published knowledge-base
  documents for policy/FAQ-style questions.
- **`search_catalog`** — literal word-match lookup for a *named* item
  ("large chicken pizza"). Tokenized per word so multi-word phrasing still
  matches (`repos/catalog.py:search_catalog`), but fundamentally a name
  search — it returns nothing for open-ended questions.
- **`browse_catalog`** — exists specifically because `search_catalog`
  can't answer "what do you have" / "what's on the menu" (no catalog item
  is ever literally named "menu"). Lists everything, optionally narrowed to
  one category by name, with subtree expansion — asking for a parent
  category ("beverages") includes its leaf categories' products
  ("Hot Coffee", "Cold Coffee"), not just products filed directly under it.
- **`create_lead`** — write-only upsert-by-conversation (`status=interested`
  as soon as intent shows, `status=new` once contact details are
  collected — calling it more than once per conversation is expected, not a
  bug). Race-safe against LangGraph running multiple tool calls from one
  turn concurrently via a Postgres advisory lock keyed on `conversation_id`.
- **`update_order`** — sets the customer's current cart. Full-replace
  semantics (the agent sends the whole cart each call, not incremental
  deltas — simpler for an LLM to reason about, mirrors `create_lead`'s
  fields-dict pattern). Prices/totals are always computed server-side from
  real catalog data, never trusted from the LLM.
- **`confirm_order`** — moves a draft order to `placed` (or, when the
  tenant reviews orders by hand, to `pending_confirmation`). This is as far
  as the agent's authority goes — **payment is never handled by the agent**,
  always a human/off-platform step afterward. Enforced server-side before it
  succeeds (not just prompted — see below): required contact info collected,
  a fulfillment type set that this tenant actually offers, a delivery
  address for delivery orders, and the tenant's minimum order value met.

### Why Lead and Order are separate entities

Settled via design discussion this session, not an obvious default: a
`Lead` is a sales-pipeline record (`interested → new → contacted →
converted → lost` — "is this person worth following up with") that doesn't
require a cart. An `Order` is a fulfillment-pipeline record
(`draft → placed → completed/cancelled` — "what was agreed, has it
shipped") that doesn't require a name/phone yet. Not every lead ever builds
a cart; not every tenant on this platform even sells catalog items an agent
could cart up. They link via `Order.lead_id`, attached automatically and
symmetrically by both `repos/orders.py` and `repos/leads.py` whichever tool
gets called first for a conversation (handles LangGraph's concurrent
same-turn tool calls without relying on call order).

`OrderStatus` is `draft → placed → completed/cancelled`, plus
`pending_confirmation` between `draft` and `placed` in human-confirmation
mode (staff confirm or reject it from the Orders page). Each order also
snapshots `currency_code` when created so a later currency change can't
relabel history.

`Order.fulfillment` is schema-free JSONB, not fixed delivery/pickup
columns — e.g. `{"type": "delivery", "address": "...", "needed_by": "..."}`
or `{"type": "pickup", "time": "..."}`. Deliberately no appointment/slot-
capacity system (no double-booking prevention) — the platform's near-term
target is social-selling businesses (cake makers, online sellers) with
delivery/pickup fulfillment, not appointment-based services; that gap is
noted, not silently patched over, should an appointment-based vertical
become a real target later.

### Guardrails — the recurring lesson: prompt instructions alone aren't reliable

Three places in `bot_engine.py`/`repos/` where a fact the LLM could get
wrong is checked mechanically, not just requested in the system prompt:

1. **Pricing guardrail** (`_apply_pricing_guardrail`) — after generation,
   any amount in the tenant's currency (recognized by `services/money.py`,
   compared numerically) in the reply must appear in this turn's trusted
   tool output (`search_catalog`/`browse_catalog`/`update_order`/
   `confirm_order` combined), or be the tenant's minimum order value or a
   shortfall against it (both legitimately quoted from the prompt);
   otherwise the reply is discarded for the tool's own text (with internal
   `[variant_id: ...]` tags stripped — this leaked into a customer-facing
   reply once before that fix).
2. **Order-confirmation guardrail** (`_apply_order_confirmation_guardrail`)
   — if the reply claims the order is confirmed/placed but `confirm_order`
   wasn't actually called and didn't succeed this thread, the claim is
   replaced. Found by testing: the LLM said "your order is confirmed"
   while the DB still showed `status=draft`. Mode-aware: in
   human-confirmation mode a successful `confirm_order` only *submits*, so a
   "confirmed/placed" claim is always replaced with the accurate "submitted"
   message.
3. **Server-side enforcement in `repos/orders.py`'s `confirm_order`** —
   raises `MissingRequiredContactInfo`, `MissingFulfillmentInfo`,
   `FulfillmentTypeNotOffered`, `MissingFulfillmentDetail` (delivery needs an
   address) and `BelowMinimumOrder` instead of trusting the agent to have
   handled them. `update_order` also rejects a fulfillment type the tenant
   doesn't offer up front. `MissingRequiredContactInfo`
   checks this tenant's dashboard-configured *required* `LeadFieldDef`s
   (not hardcoded "name"/"phone" — whatever a tenant actually marked
   required), so it generalizes per tenant rather than assuming every
   business wants the same fields.

## 5. Settings: admin-settable vs tenant-settable

Per-tenant behavior is configured in two write-separated tables (both
one-row-per-tenant, keyed by `tenant_id`; `models/settings.py`), plus a third
layer nobody sets per tenant:

| Layer | Who writes | Examples |
|---|---|---|
| **Platform constants** (`project_config.yaml`) | nobody per tenant | guardrails, RAG threshold, the payment-boundary rule, default model |
| **Admin settings** (`tenant_admin_settings`) | superadmin only, at onboarding (`/superadmin/tenants/{id}/settings`) | `currency_code`, entitlements (`ordering/catalog/documents/leads_allowed`), `allowed_channels`, `llm_model`, quotas (`monthly_message_limit`, `max_documents` — stored, **not enforced**), `api_secret` key issuance |
| **Tenant settings** (`tenant_settings`) | the tenant, from the dashboard (`/tenant/settings`) | `timezone`; persona (`bot_name`, `tone`, `language`, welcome/fallback messages, `custom_instructions`); `bot_enabled` + feature toggles; ordering rules (`delivery_enabled`, `pickup_enabled`, `cash_on_delivery`, `min_order_value`, `negotiation_mode`, `order_confirmation_mode`); notifications (`notify_emails`, `notify_new_lead/order`) |

Why currency is admin-only: orders store bare numbers with no currency, so a
tenant editing it later would silently relabel history (orders now also
snapshot `currency_code`). Tenants get **no** API-key or widget-key
management at all — `api_secret` keys are admin-issued
(`/superadmin/tenants/{id}/api-keys`), and `/widget-test` is an admin debug
tool, not a tenant feature.

**The split is enforced at the schema layer**, like `LeadUpdate`:
`TenantSettingsUpdate` and `AdminSettingsUpdate` both set `extra="forbid"`, so
a tenant sending an admin field (e.g. `currency_code`) gets a 422, not a
silent ignore. Repos mirror it: `repos/settings_read.py` (reads only),
`repos/settings.py` (tenant writes), `repos/settings_admin.py` (superadmin
writes).

**Effective settings** (`services/settings_resolver.py`) — the only settings
module the bot, notifications and dashboard layout import — merges both tables
into one frozen `EffectiveSettings`, with the rule *effective toggle = admin
allowed AND tenant enabled* (a tenant can switch off what the admin granted,
never on what wasn't). Small in-process TTL cache (30s), invalidated on every
settings write in that process. Note the invalidation is per-process: anything
that writes settings from a *different* process (scripts, the eval harness)
must go through the API, or the running server won't see it for up to the TTL.

**How settings reach the bot** (`services/prompt_builder.py`,
`bot_engine.py`, `bot_tools.py`):
- The system prompt is assembled per request from sections in
  `project_config.yaml` (`agent.prompt`), so it only describes tools the
  tenant's agent actually has and reflects that tenant's rules: current
  date/time in the tenant's timezone (the bot otherwise has no clock),
  currency, offered fulfillment types, minimum order, cash-on-delivery,
  negotiation policy, human-vs-bot confirmation wording, persona.
  `custom_instructions` are appended *after* the non-negotiable rules.
- `build_tools` filters the toolset the same way. `ordering_enabled=false`
  (or no catalog) gives a lead-only assistant.
- `bot_enabled=false`: the customer's message is still stored (staff see it
  in Conversations) but the agent is skipped and `reply` is `""`.
- `allowed_channels`: a channel the admin hasn't enabled is a 403 at
  `POST /bot/message`. `llm_model` picks the per-tenant model.
- Payment carve-out: with `cash_on_delivery` on, the bot may *state* "cash on
  delivery" for delivery orders but still never collects or discusses payment
  details.
- Negotiation: `fixed` = never quote a changed price; `escalate` = the bot must
  record the customer's requested price (order notes, or a `negotiation_request`
  lead field) before saying it passed it on. There is no live human handoff yet.
- Human confirmation mode adds the `pending_confirmation` order state and an
  Orders-page "Pending" tab with Confirm/Reject; the notification email uses
  "awaiting your confirmation" wording.

**Onboarding**: `TenantCreate` requires `currency_code` (plus optional initial
`timezone` and an `admin_settings` block); `onboard_tenant` seeds both rows.
There is no superadmin UI — admin settings and API keys are API-only for now.

## 6. RAG (`components/rag/`)

`get_rag()` returns a hybrid retriever (dense embedding search + BM25,
reciprocal rank fusion) over `DocumentChunk` rows. Documents go through a
draft → publish lifecycle (`services/publishing.py`): chunking
(`services/chunking.py`, `RecursiveCharacterTextSplitter`), embedding
(`services/embeddings.py`, OpenAI), and a "safe publish" pattern — new
chunks insert as inactive, activate atomically only once every chunk in the
batch has embedded successfully, and the previous active set is deleted in
the same swap.

Documents support an optional `active_from`/`active_until` window
(seasonal/temporary content, e.g. a holiday promo) — every RAG search
function filters through `_within_active_window()`
(`repos/documents.py`), so a document is instantly excluded/included at its
boundaries with no scheduled sweep needed for correctness; a lazy
`sweep_expired_documents()` call on read just keeps the dashboard's
displayed status from looking stale.

## 7. Catalog

`Category` (self-referencing tree) → `Product` → `Variant` (every sellable
item is a variant row, including single-variant "standalone" products).
`CategoryAttribute` is the variant-generation reuse mechanism: a category
(e.g. "Pizza") defines a reusable attribute ("Size" → [Small, Medium,
Large]); products under it or any descendant category inherit it
(`get_effective_attributes`'s ancestor-chain walk, deepest-wins override) —
deliberately no separate "product template" entity, since the category tree
already gives every product a natural inheritance path. `search_catalog`
and `browse_catalog` both live in `repos/catalog.py`; the latter's category
filter expands to the full matched subtree (see §4).

## 8. Dashboard (`client_ui/`)

Next.js App Router, Tailwind v4. Established UI pattern used across every
data page: a list (with status-tab filters) on the left, a detail panel on
the right, selection driven by a URL query param
(`?document=<id>`/`?order=<id>`/etc.) rather than route navigation, so
selecting an item never loses the list's scroll/filter state.
`router.refresh()` after mutations resyncs server-fetched sibling data.
In-app `ConfirmDialog`/`useConfirm()` replaces all native
`window.confirm()`.

Pages: **Overview**, **Leads**, **Catalog** (category tree +
attribute-based variant generation), **Knowledge Base** (documents +
temporary/seasonal document support), **Conversations** (read-only
transcript viewer), **Orders** (staff can move `placed → completed`/
`cancelled`, never back into bot-owned `draft`/`placed` states).
**Orders** also has a "Pending" tab (human-confirmation mode) with
Confirm/Reject. **Settings** (tenant-editable form: business & assistant,
feature toggles, ordering & delivery, notifications, plus a read-only
"Your plan" panel showing the admin-set currency/entitlements; deliberately no
API keys). Every price is formatted in the tenant's currency via a
`CurrencyProvider` set once in the `(app)` layout (an order uses its own
snapshotted `currency_code`).

A standalone `/widget-test` page (outside the dashboard's auth, like a real
embedded site widget) exercises `POST /bot/message` directly through a
server-side proxy route that holds the `api_secret` key
(`BOT_API_SECRET` in `client_ui/.env.local`) so the browser never sees it.

## 9. `eval/` harness

Three pieces, deliberately decoupled:

- **`eval/scenarios.yaml`** — a persona (instructions for a simulated
  customer) + `success_criteria` (graded later) per scenario. A scenario may
  carry a `settings:` block (`tenant:`/`admin:` overrides) that the harness
  applies through the real settings APIs before the conversation and restores
  afterwards, so each setting has regression coverage.
- **`eval/conversation_agent.py`** — an LLM plays the persona, driving a
  real multi-turn conversation against the actual `POST /bot/message`
  endpoint (the same path a real channel adapter would use). Saves the
  transcript plus a direct DB snapshot (`Lead`/`Order` rows) — ground truth,
  not the chat's own account of what happened.
- **`eval/eval_agent.py`** — a separate LLM judge grades a saved transcript
  against its scenario's criteria, any time later, without re-running the
  conversation.

**Known, documented limitation:** the judge (even the stronger `gpt-4o`,
after several rounds of explicit counter-instruction in the prompt) can
still claim an order "wasn't really confirmed yet" while quoting its own
`db_facts` showing `status="placed"` — a persistent bias against trusting
an assistant's own "confirmed!" language, not something prompting alone
fully eliminated. `eval_agent.py` mitigates this mechanically: any judge
issue matching a "confirmed...before..." pattern is checked against that
run's actual `db_snapshot`, and flagged `SUSPECT` in the summary
(`eval/eval_agent.py --summary`) instead of presented as a trustworthy
finding if it contradicts the ground truth. Treat `fail`/`partial` verdicts,
and especially their listed `issues`, as a first-pass signal to go read the
transcript yourself — not as an authoritative result.

## 10. Known gaps / deliberately out of scope

- **No superadmin UI** — admin settings and `api_secret` keys are managed
  via the `/superadmin` API only.
- **Quotas not enforced** — `monthly_message_limit`/`max_documents` are
  stored but nothing counts against them yet.
- **No live human handoff** — negotiation `escalate` only records the request;
  `bot_enabled=false` is the only takeover switch.
- **`tzdata`** is present transitively but not declared in `pyproject.toml`;
  Windows needs it for `zoneinfo` (timezones). Declare it if `uv sync` ever
  drops it.
- **Real channel wiring** — `ConversationChannel` models
  `website_widget`/`facebook`/`instagram`/`whatsapp`, and everything is
  channel-agnostic by design (the bot just receives
  `{channel_type, external_user_id, text}`), but only `website_widget` has
  ever actually been exercised end-to-end. The original plan's `n8n`
  inbox-integration phase (`.claude/plan/10-inbox-channel-n8n.md`) was
  never built.
- **No appointment/slot-capacity system** — deliberate, see §4.
- **No dashboard read/update for `LeadFieldDef`-driven order confirmation
  requirements beyond what already exists** — the Leads page manages
  required fields; there's no dedicated UI moment explaining that these
  same fields gate order confirmation.

## 11. Environment gotchas

See [AGENTS.md](AGENTS.md)'s "Environment gotchas" section — kept there
since it's about *how to run things*, not *what the system is*.
