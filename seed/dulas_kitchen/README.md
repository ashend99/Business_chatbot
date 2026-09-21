# Dula's Kitchen -- seed data

Sample Documents + Catalog content for a fictional F&B business ("Dula's
Kitchen"): dine-in/takeaway/in-house delivery, open 5:00 PM - 12:00 AM daily,
plus PickMe Food & Uber Eats for orders outside the direct delivery radius.
Pricing is in LKR (Sri Lankan rupees), consistent with PickMe being a Sri
Lankan platform.

These files mirror what is currently in the `dulas_kitchen` tenant's
database (the catalog was last synced from the DB on 2026-09-21; the
documents were compared against the DB at the same time and were already
identical). Seed them into a tenant with:

```
python seed/seed_business.py --slug dulas_kitchen
python seed/seed_business.py --slug dulas_kitchen --publish   # also chunk + embed the documents
```

Re-running is safe: anything that already exists (categories by name+parent,
products by name, documents by title) is left alone.

## Files

- `settings.json` -- `currency_code` (`LKR`) and initial `timezone`
  (`Asia/Colombo`). Used only when the tenant has no settings rows yet: the
  currency is an admin-only setting, so it is set here rather than left to
  default to USD.

- `documents.json` -- 6 entries, each matching `DocumentCreate`
  (`src/app/schemas/documents.py`): `title`, `content_source: "paste"`,
  `tags`, `draft_content`. Seeded as drafts; `--publish` (or
  `POST /tenant/documents/{id}/publish`) is what actually chunks + embeds
  them for RAG.

  Covers: business hours & location, dine-in/takeaway/delivery mechanics,
  PickMe Food & Uber Eats specifics, refund/cancellation policy, FAQ, and
  reservations/group bookings.

- `categories.json` -- 7 categories in two trees: `Main Course` -> Fried
  Rice / Kottu / Pizza, and `Beverages` -> Hot Coffee / Cold Coffee.

  A category may carry `attributes`: reusable variant-building blocks that
  every product under it (or a descendant category) inherits. `Main Course`
  defines `Size` -> Small / Medium / Large, so Fried Rice, Kottu and Pizza all
  offer it. (Not every product uses every choice -- Kottu and Pizza only sell
  Small and Large.)

- `products.json` -- 15 products / 25 variants, each variant matching
  `VariantCreate` (`name`, `price`, `stock_status`, optional `sku`,
  `stock_qty`, `stock_message`). Variants generated from a category attribute
  carry `attribute_values` (e.g. `{"Size": "Large"}`), which records which
  attribute choice the variant represents. Beverages are single-variant
  products whose variant is named after the drink. Every item is currently
  `in_stock`.

## The `key` / `parent_key` / `category_key` convention

`categories.json` and `products.json` use a local `key` string instead of a
real UUID, since categories don't have real ids until they're actually
created. `seed/seed_business.py`:

1. Creates categories in an order where each category's `parent_key` (if not
   `null`) has already been created, and remembers `key -> real category id`
   (setting `attributes` on newly created categories).
2. Creates products, resolving each product's `category_key` to the real
   category id from step 1.

`key`/`parent_key`/`category_key` are not real API fields -- they only exist
in these files.
