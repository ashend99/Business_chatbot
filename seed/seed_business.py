"""Seed Documents + Catalog content for a business from seed/<slug>/*.json.

Run with:
    python seed/seed_business.py --slug dulas_kitchen
    python seed/seed_business.py --slug dulas_kitchen --publish
    python seed/seed_business.py --slug another_business --name "Another Business" --email owner@example.com

Each `--slug` corresponds to a directory under seed/ holding up to four
files (all optional -- whichever are present get seeded): documents.json,
categories.json, products.json, settings.json. See
seed/dulas_kitchen/README.md for the exact shape each file must match.

The slug doubles as the tenant's `tenants.slug` -- the tenant (and one
TenantAdmin login, so you can view the seeded data immediately) is created
if it doesn't exist yet, or reused if it does.

Re-running for the same slug is safe: categories are matched by
(name, parent), products by name, and documents by title -- anything that
already exists is left alone, so adding new items to the JSON files and
re-running only picks up what's new.

--publish also publishes each newly created document (chunks + embeds it),
which calls the real OpenAI embeddings API -- costs a little money and
needs a real OPENAI_API_KEY. Omitted by default so documents land as
drafts for review first.
"""

import argparse
import asyncio
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.catalog import StockStatus
from app.models.documents import ContentSource
from app.models.tenants import Tenant
from app.repos import catalog as catalog_repo
from app.repos import documents as documents_repo
from app.repos import settings_admin as settings_admin_repo
from app.repos import tenants as tenants_repo

SEED_ROOT = Path(__file__).resolve().parent


def _load_json(slug: str, filename: str) -> list[dict] | None:
    path = SEED_ROOT / slug / filename
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


async def _get_or_create_tenant(
    session: AsyncSession, *, slug: str, name: str, email: str, username: str, password: str
) -> Tenant:
    tenant = await tenants_repo.get_tenant_by_slug(session, slug)
    if tenant is not None:
        print(f"Reusing existing tenant '{tenant.name}' (slug={slug})")
    else:
        tenant = await tenants_repo.create_tenant(session, name=name, slug=slug, email=email)
        print(f"Created tenant '{tenant.name}' (slug={slug})")

    admin = await tenants_repo.get_tenant_admin_by_tenant_id(session, tenant.id)
    if admin is None:
        await tenants_repo.create_tenant_admin(
            session, tenant_id=tenant.id, username=username, hashed_password=hash_password(password)
        )
        print(f"Created login: username={username!r} password={password!r}")
    else:
        print(f"Existing login: username={admin.username!r} (password unchanged)")

    return tenant


async def _ensure_settings(session: AsyncSession, tenant_id: uuid.UUID, seed_settings: dict | None) -> None:
    """Every tenant needs its admin + tenant settings rows (onboarding creates
    them; this script creates tenants directly, so it must too). Currency and
    timezone come from settings.json -- currency is admin-only and matters
    (orders store bare numbers), so it shouldn't silently default to USD for a
    business priced in something else. Existing rows are left untouched."""
    if await settings_admin_repo.get_admin_settings(session, tenant_id) is not None:
        print("Settings: already present")
        return
    seed_settings = seed_settings or {}
    await settings_admin_repo.create_default_settings(
        session,
        tenant_id,
        currency_code=seed_settings.get("currency_code", "USD"),
        timezone=seed_settings.get("timezone", "UTC"),
    )
    print(f"Settings: created (currency={seed_settings.get('currency_code', 'USD')})")


async def _seed_categories(session: AsyncSession, tenant_id: uuid.UUID, categories: list[dict]) -> dict[str, uuid.UUID]:
    """Topologically create categories (parents before children), matching
    existing rows by (name, parent) so a re-run doesn't duplicate them.
    Returns the local `key` -> real category id mapping products need."""
    existing = await catalog_repo.list_categories(session, tenant_id)
    by_name_parent = {(c.name, c.parent_id): c.id for c in existing}
    key_to_id: dict[str, uuid.UUID] = {}

    remaining = list(categories)
    created = 0
    while remaining:
        still_remaining = []
        progressed = False
        for cat in remaining:
            parent_key = cat.get("parent_key")
            if parent_key is not None and parent_key not in key_to_id:
                still_remaining.append(cat)
                continue

            parent_id = key_to_id.get(parent_key) if parent_key else None
            existing_id = by_name_parent.get((cat["name"], parent_id))
            if existing_id is not None:
                key_to_id[cat["key"]] = existing_id
            else:
                row = await catalog_repo.create_category(
                    session, tenant_id, name=cat["name"], parent_id=parent_id, sort_order=cat.get("sort_order", 0)
                )
                key_to_id[cat["key"]] = row.id
                created += 1
                # reusable variant-building attributes (e.g. Size -> [Small, Medium, Large]);
                # products under this category (or a descendant) inherit them. Only set for
                # newly created categories -- an existing one's attributes are the tenant's to edit.
                if cat.get("attributes"):
                    await catalog_repo.replace_category_attributes(session, tenant_id, row.id, cat["attributes"])
            progressed = True

        if not progressed:
            unresolved = [c["key"] for c in still_remaining]
            raise ValueError(f"could not resolve parent_key for categories: {unresolved} -- missing or cyclic parent_key?")
        remaining = still_remaining

    print(f"Categories: {created} created, {len(categories) - created} already existed")
    return key_to_id


async def _seed_products(
    session: AsyncSession, tenant_id: uuid.UUID, products: list[dict], category_ids: dict[str, uuid.UUID]
) -> int:
    existing_names = {p.name for p in await catalog_repo.list_products(session, tenant_id)}
    created = 0
    for prod in products:
        if prod["name"] in existing_names:
            continue

        category_id = category_ids.get(prod["category_key"]) if prod.get("category_key") else None
        if prod.get("category_key") and category_id is None:
            raise ValueError(f"unresolved category_key {prod['category_key']!r} for product {prod['name']!r}")

        variants = [
            {
                "name": v.get("name"),
                "sku": v.get("sku"),
                "price": Decimal(str(v["price"])),
                "stock_status": StockStatus(v.get("stock_status", "in_stock")),
                "stock_qty": v.get("stock_qty"),
                "stock_message": v.get("stock_message"),
                # which attribute choice the variant represents, e.g. {"Size": "Large"}
                "attribute_values": v.get("attribute_values"),
            }
            for v in prod["variants"]
        ]
        await catalog_repo.create_product(
            session,
            tenant_id,
            name=prod["name"],
            category_id=category_id,
            description=prod.get("description"),
            image_url=prod.get("image_url"),
            variants=variants,
        )
        created += 1

    print(f"Products: {created} created, {len(products) - created} already existed")
    return created


async def _seed_documents(session: AsyncSession, tenant_id: uuid.UUID, documents: list[dict], *, publish: bool) -> int:
    existing_docs, _total = await documents_repo.list_documents(session, tenant_id, page=1, page_size=1000)
    existing_titles = {d.title for d in existing_docs}

    created = 0
    for doc in documents:
        if doc["title"] in existing_titles:
            continue

        document = await documents_repo.create_document(
            session,
            tenant_id=tenant_id,
            title=doc["title"],
            content_source=ContentSource(doc.get("content_source", "paste")),
            tags=doc.get("tags"),
            draft_content=doc.get("draft_content", ""),
        )
        created += 1

        if publish:
            from app.services.publishing import PublishError, publish_document

            try:
                await publish_document(session, tenant_id, document.id)
                print(f"  published '{document.title}'")
            except PublishError as exc:
                print(f"  skipped publishing '{document.title}': {exc}")
            except Exception as exc:  # noqa: BLE001 -- report and keep seeding the rest
                print(f"  publish failed for '{document.title}': {exc}")

    print(f"Documents: {created} created, {len(documents) - created} already existed")
    return created


async def seed(args: argparse.Namespace) -> None:
    documents = _load_json(args.slug, "documents.json")
    categories = _load_json(args.slug, "categories.json")
    products = _load_json(args.slug, "products.json")
    seed_settings = _load_json(args.slug, "settings.json")

    if documents is None and categories is None and products is None:
        raise SystemExit(
            f"No seed files found under seed/{args.slug}/ "
            "(expected documents.json / categories.json / products.json)"
        )

    default_name = args.slug.replace("_", " ").replace("-", " ").title()

    async with AsyncSessionLocal() as session:
        tenant = await _get_or_create_tenant(
            session,
            slug=args.slug,
            name=args.name or default_name,
            email=args.email or f"{args.slug}@example.com",
            username=args.username,
            password=args.password,
        )
        await session.commit()

        await _ensure_settings(session, tenant.id, seed_settings)
        await session.commit()

        category_ids: dict[str, uuid.UUID] = {}
        if categories:
            category_ids = await _seed_categories(session, tenant.id, categories)
            await session.commit()

        if products:
            await _seed_products(session, tenant.id, products, category_ids)
            await session.commit()

        if documents:
            await _seed_documents(session, tenant.id, documents, publish=args.publish)
            await session.commit()

    print(f"\nDone. Tenant slug={args.slug!r} -- login username={args.username!r} password={args.password!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--slug",
        required=True,
        help="Seed data directory under seed/, and the tenant's slug (e.g. dulas_kitchen)",
    )
    parser.add_argument("--name", help="Tenant display name if creating a new tenant (default: title-cased slug)")
    parser.add_argument("--email", help="Tenant contact email if creating a new tenant (default: <slug>@example.com)")
    parser.add_argument("--username", default="demo", help="Dashboard login username if creating a new admin (default: demo)")
    parser.add_argument(
        "--password", default="changeme123", help="Dashboard login password if creating a new admin (default: changeme123)"
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also publish each newly created document (calls the OpenAI embeddings API)",
    )
    args = parser.parse_args()
    asyncio.run(seed(args))


if __name__ == "__main__":
    main()
