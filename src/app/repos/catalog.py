import uuid
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Category, CategoryAttribute, Product, StockStatus, Variant
from app.repos.tenant_scope import tenant_scope

# ---- categories ------------------------------------------------------


async def create_category(
    session: AsyncSession, tenant_id: uuid.UUID, *, name: str, parent_id: uuid.UUID | None = None, sort_order: int = 0
) -> Category:
    category = Category(tenant_id=tenant_id, name=name, parent_id=parent_id, sort_order=sort_order)
    session.add(category)
    await session.flush()
    return category


async def get_category(session: AsyncSession, tenant_id: uuid.UUID, category_id: uuid.UUID) -> Category | None:
    stmt = select(Category).where(Category.id == category_id, tenant_scope(Category.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_categories(session: AsyncSession, tenant_id: uuid.UUID) -> list[Category]:
    stmt = select(Category).where(tenant_scope(Category.tenant_id, tenant_id)).order_by(Category.sort_order, Category.name)
    return list((await session.execute(stmt)).scalars().all())


async def update_category(session: AsyncSession, tenant_id: uuid.UUID, category_id: uuid.UUID, **fields: object) -> Category | None:
    category = await get_category(session, tenant_id, category_id)
    if category is None:
        return None
    for key, value in fields.items():
        if value is not None:
            setattr(category, key, value)
    await session.flush()
    return category


async def delete_category(session: AsyncSession, tenant_id: uuid.UUID, category_id: uuid.UUID) -> bool:
    category = await get_category(session, tenant_id, category_id)
    if category is None:
        return False
    await session.delete(category)
    await session.flush()
    return True


def _is_descendant(by_parent: dict[uuid.UUID | None, list[Category]], ancestor_id: uuid.UUID, candidate_id: uuid.UUID) -> bool:
    """True if candidate_id appears anywhere below ancestor_id in the tree."""
    stack = list(by_parent.get(ancestor_id, []))
    while stack:
        node = stack.pop()
        if node.id == candidate_id:
            return True
        stack.extend(by_parent.get(node.id, []))
    return False


async def reparent_category(
    session: AsyncSession, tenant_id: uuid.UUID, category_id: uuid.UUID, new_parent_id: uuid.UUID | None
) -> Category | None:
    """Raises ValueError on a cycle attempt (new_parent_id is the category
    itself, or one of its own descendants) -- not enforceable as a DB
    constraint, per the plan."""
    category = await get_category(session, tenant_id, category_id)
    if category is None:
        return None

    if new_parent_id is not None:
        if new_parent_id == category_id:
            raise ValueError("a category cannot be its own parent")
        all_categories = await list_categories(session, tenant_id)
        by_parent: dict[uuid.UUID | None, list[Category]] = {}
        for c in all_categories:
            by_parent.setdefault(c.parent_id, []).append(c)
        if _is_descendant(by_parent, category_id, new_parent_id):
            raise ValueError("cannot reparent a category under its own descendant")

    category.parent_id = new_parent_id
    await session.flush()
    return category


async def get_category_tree(session: AsyncSession, tenant_id: uuid.UUID) -> list[dict]:
    """Fetch all categories in one query and build the nested tree in
    Python -- simpler and fast enough at this scale than a recursive CTE."""
    categories = await list_categories(session, tenant_id)
    nodes: dict[uuid.UUID, dict] = {
        c.id: {"id": c.id, "name": c.name, "parent_id": c.parent_id, "sort_order": c.sort_order, "children": []}
        for c in categories
    }
    roots: list[dict] = []
    for c in categories:
        node = nodes[c.id]
        parent_node = nodes.get(c.parent_id) if c.parent_id is not None else None
        (parent_node["children"] if parent_node is not None else roots).append(node)
    return roots


# ---- category attributes -----------------------------------------------
# The reusable "variant-building blocks" a category offers, e.g. "Pizza"
# defining Size -> [Small, Medium, Large]. See get_effective_attributes for
# how a product's category inherits these up the tree.


async def list_category_attributes(
    session: AsyncSession, tenant_id: uuid.UUID, category_id: uuid.UUID
) -> list[CategoryAttribute]:
    """This category's own attribute definitions only (not inherited) --
    what the "manage attributes" editor reads and replaces."""
    stmt = (
        select(CategoryAttribute)
        .where(tenant_scope(CategoryAttribute.tenant_id, tenant_id), CategoryAttribute.category_id == category_id)
        .order_by(CategoryAttribute.sort_order, CategoryAttribute.name)
    )
    return list((await session.execute(stmt)).scalars().all())


async def replace_category_attributes(
    session: AsyncSession, tenant_id: uuid.UUID, category_id: uuid.UUID, attributes: list[dict]
) -> list[CategoryAttribute]:
    """Full replace (PUT semantics), same pattern as leads_admin's
    replace_lead_field_defs -- a category's attribute list is small and
    edited rarely, so delete-all-then-recreate is simpler than diff/merge."""
    existing = await list_category_attributes(session, tenant_id, category_id)
    for row in existing:
        await session.delete(row)
    await session.flush()

    rows = [
        CategoryAttribute(
            tenant_id=tenant_id,
            category_id=category_id,
            name=a["name"],
            choices=a["choices"],
            sort_order=a.get("sort_order", i),
        )
        for i, a in enumerate(attributes)
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def get_effective_attributes(
    session: AsyncSession, tenant_id: uuid.UUID, category_id: uuid.UUID
) -> list[CategoryAttribute]:
    """This category's own attributes plus everything inherited from its
    ancestors, walking up parent_id. On a name collision the definition
    closest to `category_id` wins (a subcategory can override, not just
    add to, an inherited attribute). Two queries regardless of tree depth:
    all categories once (to build the parent chain in Python, avoiding a
    round trip per level), then one attribute fetch across that whole chain."""
    categories = await list_categories(session, tenant_id)
    parent_by_id = {c.id: c.parent_id for c in categories}
    if category_id not in parent_by_id:
        return []

    chain: list[uuid.UUID] = []
    current: uuid.UUID | None = category_id
    seen: set[uuid.UUID] = set()
    while current is not None and current not in seen:
        seen.add(current)
        chain.append(current)
        current = parent_by_id.get(current)

    stmt = select(CategoryAttribute).where(
        tenant_scope(CategoryAttribute.tenant_id, tenant_id), CategoryAttribute.category_id.in_(chain)
    )
    rows = (await session.execute(stmt)).scalars().all()
    by_category: dict[uuid.UUID, list[CategoryAttribute]] = {}
    for attr in rows:
        by_category.setdefault(attr.category_id, []).append(attr)

    # chain runs most-specific (the category itself) -> least-specific (root);
    # dict.setdefault keeps the first write, i.e. the closest definition.
    by_name: dict[str, CategoryAttribute] = {}
    for cid in chain:
        for attr in sorted(by_category.get(cid, []), key=lambda a: a.sort_order):
            by_name.setdefault(attr.name, attr)
    return list(by_name.values())


# ---- products / variants ----------------------------------------------


async def create_product(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str,
    category_id: uuid.UUID | None = None,
    description: str | None = None,
    image_url: str | None = None,
    variants: list[dict] | None = None,
) -> Product:
    """Auto-creates exactly one default Variant (named after the product,
    using whatever price/sku/stock fields the caller passed alongside it)
    when `variants` is empty -- every sellable item is a variant row, even a
    standalone product with no real variation."""
    product = Product(tenant_id=tenant_id, name=name, category_id=category_id, description=description, image_url=image_url)
    session.add(product)
    await session.flush()

    for spec in variants or [{}]:
        variant = Variant(
            tenant_id=tenant_id,
            product_id=product.id,
            name=spec.get("name") or name,
            sku=spec.get("sku"),
            price=spec["price"],
            stock_status=spec.get("stock_status", StockStatus.IN_STOCK),
            stock_qty=spec.get("stock_qty"),
            stock_message=spec.get("stock_message"),
            attribute_values=spec.get("attribute_values"),
        )
        session.add(variant)
    await session.flush()
    return product


async def get_product(session: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID) -> Product | None:
    stmt = select(Product).where(Product.id == product_id, tenant_scope(Product.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_products(session: AsyncSession, tenant_id: uuid.UUID, *, category_id: uuid.UUID | None = None) -> list[Product]:
    stmt = select(Product).where(tenant_scope(Product.tenant_id, tenant_id))
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    stmt = stmt.order_by(Product.name)
    return list((await session.execute(stmt)).scalars().all())


async def update_product(session: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID, **fields: object) -> Product | None:
    product = await get_product(session, tenant_id, product_id)
    if product is None:
        return None
    for key, value in fields.items():
        if value is not None:
            setattr(product, key, value)
    await session.flush()
    return product


async def delete_product(session: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID) -> bool:
    product = await get_product(session, tenant_id, product_id)
    if product is None:
        return False
    await session.delete(product)  # cascades to variants via FK ondelete
    await session.flush()
    return True


async def get_variant(session: AsyncSession, tenant_id: uuid.UUID, variant_id: uuid.UUID) -> Variant | None:
    stmt = select(Variant).where(Variant.id == variant_id, tenant_scope(Variant.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_variants_for_product(session: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID) -> list[Variant]:
    stmt = select(Variant).where(tenant_scope(Variant.tenant_id, tenant_id), Variant.product_id == product_id).order_by(Variant.name)
    return list((await session.execute(stmt)).scalars().all())


async def add_variant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    name: str,
    sku: str | None = None,
    price: Decimal,
    stock_status: StockStatus = StockStatus.IN_STOCK,
    stock_qty: int | None = None,
    stock_message: str | None = None,
    attribute_values: dict[str, str] | None = None,
) -> Variant:
    variant = Variant(
        tenant_id=tenant_id,
        product_id=product_id,
        name=name,
        sku=sku,
        price=price,
        stock_status=stock_status,
        stock_qty=stock_qty,
        stock_message=stock_message,
        attribute_values=attribute_values,
    )
    session.add(variant)
    await session.flush()
    return variant


async def update_variant(session: AsyncSession, tenant_id: uuid.UUID, variant_id: uuid.UUID, **fields: object) -> Variant | None:
    variant = await get_variant(session, tenant_id, variant_id)
    if variant is None:
        return None
    for key, value in fields.items():
        if value is not None:
            setattr(variant, key, value)
    await session.flush()
    return variant


async def delete_variant(session: AsyncSession, tenant_id: uuid.UUID, variant_id: uuid.UUID) -> bool:
    variant = await get_variant(session, tenant_id, variant_id)
    if variant is None:
        return False
    await session.delete(variant)
    await session.flush()
    return True


async def search_catalog(session: AsyncSession, tenant_id: uuid.UUID, query: str, limit: int = 10) -> list[tuple[Variant, Product, Category | None]]:
    """ILIKE search across variant/product/category name -- used by the
    dashboard search box and (Phase 4) the bot's catalog tool. Only active
    variants are returned.

    Tokenized per word (each word must match variant/product/category name
    individually, not the query as one substring) so natural phrasing like
    "large chicken pizza" still matches a "Chicken Pizza" product's "Large"
    variant -- a single `%large chicken pizza%` pattern would never match
    since no single column contains that exact phrase."""
    words = [w for w in query.split() if w]
    if not words:
        return []
    word_conditions = [
        or_(Variant.name.ilike(f"%{word}%"), Product.name.ilike(f"%{word}%"), Category.name.ilike(f"%{word}%"))
        for word in words
    ]
    stmt = (
        select(Variant, Product, Category)
        .join(Product, Product.id == Variant.product_id)
        .join(Category, Category.id == Product.category_id, isouter=True)
        .where(
            tenant_scope(Variant.tenant_id, tenant_id),
            Variant.active.is_(True),
            and_(*word_conditions),
        )
        .order_by(Product.name, Variant.name)
        .limit(limit)
    )
    return [(variant, product, category) for variant, product, category in (await session.execute(stmt)).all()]


async def browse_catalog(
    session: AsyncSession, tenant_id: uuid.UUID, *, category_name: str | None = None, limit: int = 100
) -> list[tuple[Variant, Product, Category | None]]:
    """Every active variant, optionally narrowed to one category by name --
    for the bot's browse_catalog tool. search_catalog's literal word match
    can't answer open-ended questions like "what's on the menu" or "what do
    you sell", since nothing in a real catalog is ever literally named
    "menu" or "available" -- this lists everything instead of searching
    for a term.

    A category_name match expands to that category's whole subtree: a
    parent like "Beverages" usually holds no products directly (they sit on
    leaf categories like "Hot Coffee"/"Cold Coffee" underneath it), so
    matching only the literal category a product is filed under would make
    "what beverages do you have" return nothing -- exactly the same class of
    bug this tool exists to fix for product names."""
    stmt = (
        select(Variant, Product, Category)
        .join(Product, Product.id == Variant.product_id)
        .join(Category, Category.id == Product.category_id, isouter=True)
        .where(tenant_scope(Variant.tenant_id, tenant_id), Variant.active.is_(True))
    )
    if category_name:
        matching_ids = await _expand_category_subtree_ids(session, tenant_id, category_name)
        if not matching_ids:
            return []
        stmt = stmt.where(Product.category_id.in_(matching_ids))
    stmt = stmt.order_by(Category.name, Product.name, Variant.name).limit(limit)
    return [(variant, product, category) for variant, product, category in (await session.execute(stmt)).all()]


async def _expand_category_subtree_ids(session: AsyncSession, tenant_id: uuid.UUID, name_query: str) -> set[uuid.UUID]:
    """All categories whose name matches name_query, plus every descendant
    of each match -- small tenant-scale category trees, so building it in
    Python from one flat fetch is simpler than a recursive CTE."""
    categories = await list_categories(session, tenant_id)
    children_by_parent: dict[uuid.UUID | None, list[Category]] = {}
    for c in categories:
        children_by_parent.setdefault(c.parent_id, []).append(c)

    matched_ids = {c.id for c in categories if name_query.lower() in c.name.lower()}
    result = set(matched_ids)
    stack = list(matched_ids)
    while stack:
        current_id = stack.pop()
        for child in children_by_parent.get(current_id, []):
            if child.id not in result:
                result.add(child.id)
                stack.append(child.id)
    return result
