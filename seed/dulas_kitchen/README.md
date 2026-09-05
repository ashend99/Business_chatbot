# Dula's Kitchen -- seed data

Sample Documents + Catalog content for a fictional F&B business ("Dula's
Kitchen"): dine-in/takeaway/in-house delivery, open 5:00 PM - 12:00 AM daily,
plus PickMe Food & Uber Eats for orders outside the direct delivery radius.
Pricing is in LKR (Sri Lankan rupees), consistent with PickMe being a Sri
Lankan platform.

**Not seeded yet** -- these are plain data files for review. Nothing in here
has touched the database.

## Files

- `documents.json` -- 6 entries, each matching `DocumentCreate`
  (`src/app/schemas/documents.py`): `title`, `content_source: "paste"`,
  `tags`, `draft_content`. POST each one directly to `POST /tenant/documents`
  as-is, then `POST /tenant/documents/{id}/publish` once you're happy with
  them (publishing is what actually chunks + embeds the content for RAG).

  Covers: business hours & location, dine-in/takeaway/delivery mechanics,
  PickMe Food & Uber Eats specifics, refund/cancellation policy, FAQ, and
  reservations/group bookings.

- `categories.json` -- 11 categories, a mix of top-level (`parent_key: null`)
  and one level of subcategory (`Main Course` -> Rice & Noodles / Curries /
  Grills & BBQ; `Beverages` -> Soft Drinks / Fresh Juices / Mocktails).

- `products.json` -- 28 products, each with one or more variants matching
  `VariantCreate` (`name`, `sku`, `price`, `stock_status`,
  `stock_qty`/`stock_message` where relevant). One product (Mango Juice) is
  deliberately `stock_status: "out_of_stock"` with a `stock_message`, to
  exercise that path when testing the catalog search / bot pricing guardrail.

## The `key` / `parent_key` / `category_key` convention

`categories.json` and `products.json` use a local `key` string instead of a
real UUID, since categories don't have real ids until they're actually
created via `POST /tenant/categories`. Whatever seeds this data needs to:

1. Create categories in an order where each category's `parent_key` (if not
   `null`) has already been created, and remember `key -> real category id`.
2. Create products via `POST /tenant/products`, resolving each product's
   `category_key` to the real category id from step 1 (send it as
   `category_id` in the `ProductCreate` payload, alongside `variants`).

`key`/`parent_key`/`category_key` are not real API fields -- strip them
before sending; only `name`, `parent_id`/`category_id`, `sort_order`,
`variants`, etc. go over the wire.
