# Phase 4 — Bot Core Engine (Intent Routing, RAG, Catalog Lookup)

## Goal

The conversational core: given an inbound message, classify intent, answer
from Documents (RAG) or Catalog (direct lookup), or drive the lead-capture
state machine — independent of which channel it arrived on (channel adapters
are Phases 9/10).

## Prerequisites

Phases 0, 2 (Documents/embeddings), 3 (Catalog). Phase 7 (Settings) supplies
persona/toggles — until it exists, use hardcoded defaults so this phase isn't
blocked.

## Data model

### `conversations`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk | |
| channel_type | enum(`website_widget`,`facebook`,`instagram`,`whatsapp`) | |
| external_user_id | text | visitor id / PSID / phone, depending on channel |
| status | enum(`open`,`idle`,`closed`) | |
| detected_intent | enum(`none`,`informational`,`product`,`purchase`,`fallback`) nullable | last/current detected intent |
| matched_variant_id | UUID fk → variants, nullable | set once purchase intent resolves to one item |
| lead_flow_state | enum(`none`,`intent_detected`,`awaiting_close_signal`,`collecting_fields`,`confirmed`) | drives Phase 5 handoff |
| last_message_at | timestamptz | |
| last_nudge_at | timestamptz nullable | |
| created_at | timestamptz | |

### `messages`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| conversation_id | UUID fk | |
| tenant_id | UUID | denormalized |
| role | enum(`user`,`assistant`,`system`) | |
| content | text | |
| created_at | timestamptz | |

## Request/response contract

`POST /bot/message` (internal — called by n8n or the widget backend, never
directly by end customers):

```json
// request
{
  "tenant_id": "...",
  "channel_type": "facebook",
  "external_user_id": "psid_123",
  "text": "Do you have red t-shirts in stock?"
}
```

```json
// response
{
  "reply": "Yes — Red, Large is in stock at $19.99.",
  "conversation_id": "...",
  "actions": []   // e.g. [{"type": "lead_created", "lead_id": "..."}]
}
```

Auth: internal service credential (tenant's `api_secret` key, or a shared
internal token if all callers are trusted infra you control — decide based on
whether n8n runs inside your own network boundary).

## Intent classification

Single LLM call per inbound message (small/fast model, e.g. `gpt-4o-mini`)
using structured output:

```
Classify the message into exactly one of:
informational | product | purchase | fallback
Also extract a short "catalog_query" string if the message references a
specific product/service, else null.
```

Return JSON: `{intent, confidence, catalog_query}`. If `confidence` below a
threshold (e.g. 0.5), force `fallback` regardless of the label.

## Branch: informational (RAG)

1. Embed the user message.
2. `pgvector` cosine similarity search over `document_chunks` where
   `tenant_id = ...`, `is_active = true`, top-k (e.g. 5).
3. If best similarity score is below a threshold, route to fallback instead.
4. Build a generation prompt: system prompt (persona/tone from Settings,
   defaulted for now) + retrieved chunks as context + last N conversation
   turns + the user's question.
5. Call the LLM for the final answer, return it.

## Branch: product/pricing (direct Catalog lookup)

1. Use `catalog_query` (or the raw message) against
   `GET /tenant/catalog/search` (Phase 3).
2. Zero results → fallback ("we don't carry that").
3. One unambiguous result → answer directly with price + stock (using the
   variant's `stock_message` if out of stock) — **never** paraphrased from a
   document.
4. Multiple candidates → ask one clarifying question using the category tree
   to disambiguate (e.g. "Did you mean the one under Catering or Events?"),
   store the candidate list on `conversations` (or a short-lived cache) so the
   next message resolves against it instead of re-searching from scratch.

## Branch: purchase/service intent → lead-capture state machine

State transitions on `conversations.lead_flow_state`:

1. `none → intent_detected`: purchase intent detected against a resolved
   `matched_variant_id`. Do **not** interrupt — keep answering any further
   questions normally in parallel.
2. Idle nudge: a lightweight check (can run on each subsequent inbound event,
   or a scheduled sweep) — if `lead_flow_state = intent_detected` and
   `now() - last_message_at > threshold` (e.g. 5 min) and no nudge sent yet
   (`last_nudge_at IS NULL`), send the nudge message once, set
   `last_nudge_at`.
3. `intent_detected → awaiting_close_signal → collecting_fields`: on an
   explicit closing/commitment signal from the user (detected via the same
   classification call, or a follow-up "is this a closing signal?" check),
   start asking for the tenant's configured lead fields (Phase 5) one at a
   time, conversationally.
4. `collecting_fields → confirmed`: once required fields are collected,
   summarize back to the user, call Phase 5's `create_or_update_lead(...)`
   with `status=new`, and record `actions: [{"type": "lead_created", ...}]`
   in the response for the channel adapter to know a lead resulted.
5. Abandonment at any point after `intent_detected` without reaching
   `confirmed` → a partial lead (`status=interested`) is still recorded
   (handled by Phase 5, triggered from the idle-nudge sweep or session
   timeout logic here).

## Branch: fallback

Return the tenant's configured fallback message (defaulted for now), and
offer to log the interaction the same way a partial lead would be (same code
path as intent abandonment, tagged without a matched variant).

## Feature toggles (stub until Phase 7)

Before routing, check tenant feature flags (Documents/Catalog/Leads
enabled/disabled). If a module is off, that branch is simply not reachable —
route straight to fallback instead. Hardcode all as "on" until Phase 7 wires
real settings.

## Where to implement

| File | Contents |
|---|---|
| `src/app/models/conversations.py` | `Conversation(Base, TenantScopedMixin)`, `Message(Base, TenantScopedMixin)` (`conversation_id` FK) |
| `src/app/models/__init__.py` | Import the two new classes |
| `src/app/schemas/conversations.py` | `BotMessageRequest`, `BotMessageResponse` (matches the JSON contract below) |
| `src/app/repos/conversations.py` | `get_or_create_conversation(session, tenant_id, channel_type, external_user_id)`, `add_message(session, tenant_id, conversation_id, role, content)`, `get_recent_messages(session, tenant_id, conversation_id, limit=10)`, `update_conversation_state(session, tenant_id, conversation_id, **fields)` |
| `src/app/services/intent.py` | `async def classify_intent(text, history) -> IntentResult` (dataclass/pydantic model: `intent`, `confidence`, `catalog_query`) — one OpenAI call with a structured-output/JSON-schema response format |
| `src/app/services/rag.py` | `async def retrieve_chunks(session, tenant_id, query_embedding, k=5)` (calls `repos/documents.py`'s `search_similar_chunks`), `async def generate_answer(persona, chunks, history, question) -> str` |
| `src/app/services/catalog_lookup.py` | `async def resolve_catalog_query(session, tenant_id, query) -> CatalogMatch` (zero/one/many result handling + the category-tree clarifying-question text) |
| `src/app/services/lead_flow.py` | `async def advance_lead_flow(session, tenant_id, conversation, message_text) -> LeadFlowResult` — implements the state machine transitions described below; calls into Phase 5's `create_or_update_lead_from_bot` only at the `confirmed`/abandonment points |
| `src/app/services/bot_engine.py` | `async def handle_message(session, tenant_id, channel_type, external_user_id, text) -> BotMessageResponse` — top-level orchestrator: load/create conversation → check tenant suspended/`bot_enabled` (Phase 1/7) → classify intent → dispatch to `rag.py` / `catalog_lookup.py` / `lead_flow.py` / fallback → persist messages → return reply + actions |
| `src/app/core/deps.py` | Add `get_current_service_tenant` — validates the caller's API secret key (Phase 0's `tenant_api_keys`, `key_type=api_secret`) and yields `tenant_id`, used by `/bot/message` instead of the JWT-based dependencies |
| `src/app/api/bot/router.py` | `APIRouter(prefix="/bot")`: `POST /message` calling `services/bot_engine.handle_message` — this module must not import anything from `repos/leads.py` except the single creation function, and must not import `repos/sales.py` or `repos/settings.py`'s read paths at all |

## Task checklist

1. `models/conversations.py` + migration
2. `repos/conversations.py`
3. `services/intent.py`
4. `services/rag.py` (reuses Phase 2's `search_similar_chunks` + `services/embeddings.py`)
5. `services/catalog_lookup.py` (reuses Phase 3's `search_catalog`)
6. `services/lead_flow.py` (state machine only — actual persistence added once Phase 5 exists)
7. `services/bot_engine.py` tying it together
8. `core/deps.py` service-auth dependency
9. `api/bot/router.py`, wired into `main.py`

## Test plan

- Scripted fixture conversations, one per branch:
  - Informational question answered from a known published document
  - Pricing question resolves to the correct variant's price/stock
  - Ambiguous product query triggers a clarifying question, second message resolves it
  - Purchase intent → idle gap → nudge sent exactly once
  - Purchase intent → closing signal → fields collected → `lead_created` action emitted
  - Purchase intent abandoned (session ends without closing) → partial lead path triggered
  - Out-of-scope question → fallback message, no hallucinated answer
- Retrieval correctness: seed known chunks with known embeddings, confirm top-k ordering
- Disabled Catalog toggle (stubbed) → purchase branch unreachable, falls back

## Out of scope

- Multi-turn disambiguation beyond one clarifying round
- Voice/image input
- Real feature-toggle wiring (stubbed until Phase 7)
