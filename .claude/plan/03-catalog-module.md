# Phase 3 — Catalog Module

## Goal

Structured, always-accurate product/service data: unlimited-depth category
tree, products as an optional grouping label, variants as the actual sellable
units.

## Prerequisites

Phase 0 (tenancy/auth).

## Data model

### `categories`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk | |
| parent_id | UUID fk → categories, nullable | self-referencing, unlimited depth |
| name | text | |
| sort_order | int | for stable dashboard tree ordering |
| created_at / updated_at | timestamptz | |

Guard against cycles at the application layer when reparenting (walk up from
the new parent to confirm the node itself isn't an ancestor of the new parent).

### `products`
| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| tenant_id | UUID fk | |
| category_id | UUID fk → categories, nullable | |
| name | text | display/grouping label |
| description | text nullable | |
| image_url | text nullable | |
| created_at / updated_at | timestamptz | |

### `variants`
Every sellable item is a variant row — including "standalone" products, which
simply get exactly one variant created automatically. This keeps price/stock/
SKU on a single table instead of duplicating those fields on `products` too,
and matches the FRD requirement that the bot always resolves down to one
sellable item.

| Column | Type | Notes |
|---|---|---|
| id | UUID pk | |
| product_id | UUID fk → products | |
| tenant_id | UUID | denormalized for direct scoping |
| name | text | e.g. `"Red, Large"`, or same as product name if standalone |
| sku | text nullable | |
| price | numeric(12,2) | |
| stock_status | enum(`in_stock`,`out_of_stock`,`unlimited`) | |
| stock_qty | int nullable | null when `unlimited` |
| stock_message | text nullable | custom message shown when out of stock |
| active | bool | hide without deleting |
| created_at / updated_at | timestamptz | |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST/GET/PATCH/DELETE | `/tenant/categories` (+ `/{id}`) | Tree CRUD |
| GET | `/tenant/categories/tree` | Full nested tree for the dashboard's expandable UI |
| POST | `/tenant/products` | Create product (auto-creates one default variant if none supplied) |
| GET/PATCH/DELETE | `/tenant/products/{id}` | |
| POST/GET/PATCH/DELETE | `/tenant/products/{id}/variants` (+ `/{variant_id}`) | |
| GET | `/tenant/catalog/search?q=` | Name/category-aware lookup, used by the bot engine (Phase 4) and dashboard search box |

## Where to implement

| File | Contents |
|---|---|
| `src/app/models/catalog.py` | `Category(Base, TenantScopedMixin)` (self FK `parent_id`), `Product(Base, TenantScopedMixin)`, `Variant(Base, TenantScopedMixin)` (`product_id` FK) |
| `src/app/models/__init__.py` | Import the three new classes |
| `src/app/schemas/catalog.py` | `CategoryCreate/Read/Tree`, `ProductCreate/Read`, `VariantCreate/Read` |
| `src/app/repos/catalog.py` | `get_category_tree(session, tenant_id)` — fetch all categories for the tenant in one query and build the nested tree in Python (simpler and fast enough at this scale than a recursive CTE), `reparent_category(session, tenant_id, category_id, new_parent_id)` with a cycle guard (walk up from `new_parent_id` via the in-memory tree, reject if `category_id` is among the ancestors), `create_product(session, tenant_id, ..., variants=[...])` — auto-creates one default `Variant` if the caller passes none, `search_catalog(session, tenant_id, query)` (`ILIKE` on `variants.name`/`products.name`/`categories.name` to start) |
| `src/app/api/tenant/catalog.py` | `APIRouter(prefix="/tenant")`: category CRUD + `/categories/tree`, product CRUD, variant CRUD, `/catalog/search` |

## Task checklist

1. `models/catalog.py` + migration, including the reparent cycle-guard logic in `repos/catalog.py` (not enforceable at the DB constraint level alone)
2. `repos/catalog.py`: tree fetch/build, product/variant CRUD with the auto-default-variant behavior, search
3. `api/tenant/catalog.py`, wired into `main.py`
4. Revisit `search_catalog`'s matching quality once Phase 4 is actually testing against it — upgrade to `pg_trgm` similarity if plain `ILIKE` misses too many real queries

## Test plan

- Build a 3+ level category tree, confirm tree endpoint returns correct nesting
- Attempt to reparent a category under its own descendant → rejected
- Create a product with two variants → both independently priced/stocked
- Create a standalone product with no variants supplied → exactly one variant auto-created
- Deactivate a variant → excluded from search/bot lookup, still visible in dashboard list
- Search returns the correct single variant for an unambiguous query, and multiple candidates for an ambiguous one (consumed by Phase 4's disambiguation step)

## Out of scope

- Bulk import/CSV
- External inventory/POS sync
- Multi-currency pricing
