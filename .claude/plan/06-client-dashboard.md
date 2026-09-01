# Phase 6 — Client Dashboard (Documents / Catalog / Leads)

## Goal

Build the frontend for the client-facing dashboard's data-management pages.
Settings (Phase 7) and Sales (Phase 8) pages are added to this same app in
their own phases — this phase covers the shell + Documents/Catalog/Leads.

## Prerequisites

Phases 0, 2, 3, 5 (all backing APIs).

## Recommended stack (not yet committed in code — your call)

- Next.js (App Router) + TypeScript, deployed on Vercel
- Auth: store the JWT in an httpOnly cookie set by a thin Next.js route that
  proxies to `/auth/tenant/login`; avoid storing tokens in `localStorage`
  (XSS exposure)
- Data fetching: server components for lists/detail, client components for
  interactive forms (tree editor, chat-transcript viewer)

## Sitemap

| Route | Purpose |
|---|---|
| `/login` | Tenant user login |
| `/activate` | Consumes the invite/reset token, sets password |
| `/documents` | List + filter by tag/status |
| `/documents/[id]` | Edit draft, view status, Publish button |
| `/documents/new` | Upload / paste / URL import |
| `/catalog` | Expandable category tree UI |
| `/catalog/products/[id]` | Product + its variants |
| `/leads` | List, filter/sort/search |
| `/leads/[id]` | Detail: fields, transcript, status dropdown, notes |

## Per-page requirements

**Documents list/detail**
- Status badge (`draft`/`processing`/`active`/`failed`/`inactive`)
- Edits save as draft immediately (autosave or explicit Save); Publish is a
  separate, explicit action with a confirmation ("this will re-embed and go
  live") per the FRD's staged-draft requirement
- `failed` status shows a Retry action

**Catalog tree**
- Expand/collapse nested categories, drag-or-menu based reparenting (must
  call the reparent endpoint, which rejects cycles server-side — surface that
  error clearly)
- Product view lists its variants inline with price/stock/active toggle

**Leads list/detail**
- List columns: contact info (if present), matched product/service, status,
  timestamp, conversation snippet
- Detail: dynamically render fields based on that tenant's `lead_field_defs`
  (don't hardcode name/phone/email — read the schema)
- Full transcript view (chronological `messages` for the linked conversation)
- Status dropdown limited to the fixed status set; notes as a free-text
  autosave field

## Where to implement

This is the first phase touching frontend code, which doesn't exist under
`src/app/` (that's the Python backend package). Recommended: a sibling
`dashboard/` folder at the repo root, e.g. `dashboard/` containing a standard
Next.js App Router project (`dashboard/app/...`, `dashboard/package.json`).
Keeping it in the same repo (monorepo-style, two independently deployable
projects) avoids cross-repo coordination for an MVP-stage solo/small team;
split it into its own repo later only if CI/deploy pipelines start conflicting.

| Path | Contents |
|---|---|
| `dashboard/app/login/page.tsx` | Login form → calls a Next.js route handler that proxies to `POST /auth/tenant/login`, sets the JWT as an httpOnly cookie |
| `dashboard/app/activate/page.tsx` | Reads `?token=` param, form for new password → `POST /auth/activate` |
| `dashboard/app/documents/page.tsx`, `dashboard/app/documents/[id]/page.tsx`, `dashboard/app/documents/new/page.tsx` | Bind to Phase 2's `/tenant/documents*` endpoints |
| `dashboard/app/catalog/page.tsx`, `dashboard/app/catalog/products/[id]/page.tsx` | Bind to Phase 3's `/tenant/categories*`, `/tenant/products*` endpoints |
| `dashboard/app/leads/page.tsx`, `dashboard/app/leads/[id]/page.tsx` | Bind to Phase 5's `/tenant/leads*` endpoints |
| `dashboard/lib/api.ts` | Thin fetch wrapper attaching the auth cookie/JWT to every backend call |
| `dashboard/components/...` | Shared layout/nav shell, category tree widget, lead field renderer (reads that tenant's `lead_field_defs` schema dynamically — don't hardcode name/phone/email fields in the component) |

## Task checklist

1. `dashboard/` Next.js project scaffold + auth flow (login, activate, cookie-based session, protected-route wrapper)
2. Documents pages
3. Catalog tree + product/variant pages
4. Leads list/detail pages
5. Shared layout/nav shell

## Test plan

- Playwright e2e: upload a doc → publish → status becomes `active`
- Playwright e2e: build a category → add product with 2 variants → both visible
- Playwright e2e: open a lead created via a Phase 4/5 test conversation → transcript renders, status change persists
- Manual QA pass on responsive layout (dashboard is desk-first but shouldn't break on tablet)

## Out of scope

- Real-time updates (websocket) — polling/refresh is fine for MVP
- Bulk operations UI
