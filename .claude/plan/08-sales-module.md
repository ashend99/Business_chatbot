# Phase 8 — Sales Module

## Goal

Give clients visibility into sales performance, computed entirely from Leads
data — there is no separate sales/transaction entity, since payments happen
outside the bot (per the FRD's explicit no-in-chat-payment decision).

## Prerequisites

Phase 5 (leads with `status` + `deal_value`).

## Data model

No new tables. Relies on `leads.status = 'converted'` and `leads.deal_value`
(both already defined in Phase 5).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/tenant/sales/summary` | Totals: count of converted leads, sum of `deal_value`, conversion rate (`converted / (new + contacted + converted + lost)`) over a date range |
| GET | `/tenant/sales/timeseries?range=30d` | Daily/weekly buckets of converted-lead count and revenue, for dashboard charts |
| GET | `/tenant/sales/by-product` | Breakdown grouped by `matched_variant_id` → product/variant name |

All queries filter by `tenant_id` from the JWT, plus optional date-range
query params.

## Where to implement

| File | Contents |
|---|---|
| `src/app/models/leads.py` | **Small edit from Phase 5**: add `converted_at: Mapped[datetime | None]` to `Lead`, set it when status transitions to `converted` (unambiguous date to aggregate on, instead of overloading `updated_at`) |
| `src/app/repos/sales.py` | `get_sales_summary(session, tenant_id, date_from, date_to)`, `get_sales_timeseries(session, tenant_id, date_from, date_to, granularity)` (SQL `date_trunc` grouped by `converted_at`), `get_sales_by_product(session, tenant_id, date_from, date_to)` (`GROUP BY matched_variant_id`, joined to `variants`/`products` for display names) |
| `src/app/schemas/sales.py` | `SalesSummary`, `SalesTimeseriesPoint`, `SalesByProductRow` |
| `src/app/api/tenant/sales.py` | `APIRouter(prefix="/tenant/sales")`: `/summary`, `/timeseries`, `/by-product` |
| `dashboard/app/sales/page.tsx` | Summary cards + chart + breakdown table (added to the Phase 6 dashboard app) |

## Task checklist

1. Add `converted_at` to `Lead` (small Alembic migration on top of Phase 5's table)
2. `repos/sales.py` aggregation queries
3. `api/tenant/sales.py`, wired into `main.py`
4. `dashboard/app/sales/page.tsx`

## Test plan

- Seed leads with a mix of statuses, `deal_value`s, and dates spanning
  several weeks → verify summary totals and conversion rate match hand-computed
  expectations
- Timeseries buckets align to the requested range and granularity
- By-product breakdown correctly groups multiple leads against the same variant
- Leads without `deal_value` (converted but no value entered) excluded from
  revenue sum but included in conversion count

## Out of scope

- Forecasting/projections
- External accounting/POS integration
- Multi-currency aggregation
