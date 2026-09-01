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

## Task checklist

1. Aggregation queries (SQL `GROUP BY` on date-truncated `updated_at` or a
   dedicated `converted_at` timestamp — consider adding `converted_at` to
   `leads` in a small Phase 5 follow-up migration if `updated_at` alone is
   ambiguous once multiple status changes happen)
2. Summary/timeseries/by-product endpoints
3. Dashboard page: cards for summary totals, a line/bar chart for the
   timeseries, a table for by-product breakdown

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
