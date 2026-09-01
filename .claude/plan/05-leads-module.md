# Phase 5 — Leads Module

## Goal

Dynamic, client-defined lead schema; partial (`interested`) vs full (`new`)
lead capture; a write-only creation path for the bot; full CRUD/notes for the
dashboard.

## Prerequisites

Phase 0 (tenancy), Phase 4 (bot engine drives creation), Phase 3 (variant
linking).

## Data model

### `lead_field_defs`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk | |
| field_key | text | machine key, e.g. `preferred_date` |
| label | text | client-facing label |
| field_type | enum(`text`,`phone`,`email`,`date`,`textarea`) | |
| required | bool | |
| sort_order | int | |

Seed sensible defaults per tenant at creation time (name, phone, email) —
clients can edit/remove/add from there.

### `leads`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk | |
| conversation_id | UUID fk → conversations, nullable | traceability back to the transcript |
| matched_variant_id | UUID fk → variants, nullable | |
| status | enum(`interested`,`new`,`contacted`,`converted`,`lost`) | system sets only `interested`/`new`; rest are manual |
| field_values | jsonb | `{field_key: value}` per `lead_field_defs` |
| deal_value | numeric(12,2) nullable | manually entered on conversion, feeds Phase 8 Sales |
| notes | text nullable | free-text, client-editable |
| created_at / updated_at | timestamptz | |

## Bot's write-only creation path

A single internal function, not a generic repository:

```python
async def create_or_update_lead_from_bot(
    session, tenant_id: UUID, conversation_id: UUID,
    matched_variant_id: UUID | None, field_values: dict, status: Literal["interested", "new"],
) -> Lead:
    ...
```

This is the **only** entry point the bot engine (Phase 4) calls. It has no
read/list/update capability over existing leads — it cannot query the Leads
table, only insert/upsert-by-conversation. The `/bot` router imports nothing
else from the leads module.

## Client-facing endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/tenant/leads` | List, filter by status/date range/matched product, search by name/contact |
| GET | `/tenant/leads/{id}` | Detail incl. full conversation transcript (join `messages` via `conversation_id`) |
| PATCH | `/tenant/leads/{id}` | Update `status`, `notes`, `deal_value` |
| GET/PUT | `/tenant/lead-field-defs` | Configure the dynamic schema |

## Notifications

Reuse the `EmailSender` abstraction from Phase 1:
- `status=new` → send notification (email + dashboard alert flag)
- `status=interested` → dashboard-visible only, no email (or a lighter digest — pick one; recommend none for MVP, add a daily digest later if requested)

## Task checklist

1. Models + migration, seed default field defs on tenant creation
2. `create_or_update_lead_from_bot` internal function
3. Client-facing CRUD/list/detail endpoints
4. Notification hook on `status=new`
5. Lead-field-defs config endpoints

## Test plan

- Configure custom fields (e.g. "preferred appointment date") → bot conversation collecting exactly those fields produces a lead whose `field_values` keys match
- Full close → lead `status=new`, notification triggered
- Abandonment mid-flow → lead `status=interested`, no notification
- Manual status transition via dashboard API (`new → contacted → converted` with `deal_value`)
- Confirm `/bot` router has no importable path to list/read leads (a code-level check, not just a test — verify at review time)
- Cross-tenant: lead list for tenant A never returns tenant B's rows even with a guessed ID

## Out of scope

- Automatic conversion detection
- External CRM sync
- Custom status labels beyond the fixed set (noted in the FRD as a future iteration)
