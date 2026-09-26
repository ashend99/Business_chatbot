"""repos/catalog.py: word-tokenised search, subtree browse, the category
tree (cycle prevention) and attribute inheritance."""

from decimal import Decimal

import pytest
from factories import make_catalog, make_tenant

from app.repos import catalog as catalog_repo


@pytest.fixture
async def shop(session):
    tenant = await make_tenant(session)
    return tenant, await make_catalog(session, tenant.id)


def names(rows) -> set[str]:
    return {f"{product.name} - {variant.name}" for variant, product, _category in rows}


# ---- search -----------------------------------------------------------------


@pytest.mark.parametrize("query", ["large latte", "LATTE large", "  classic   large  "])
async def test_search_matches_each_word_across_columns(session, shop, query: str) -> None:
    tenant, _ = shop
    assert names(await catalog_repo.search_catalog(session, tenant.id, query)) == {
        "Classic Latte - Large"
    }


async def test_search_matches_category_names(session, shop) -> None:
    tenant, _ = shop
    assert names(await catalog_repo.search_catalog(session, tenant.id, "cold drinks")) == {
        "Iced Tea - Iced Tea"
    }


async def test_search_excludes_inactive_but_keeps_out_of_stock(session, shop) -> None:
    tenant, _ = shop
    assert await catalog_repo.search_catalog(session, tenant.id, "scone") == []
    assert names(await catalog_repo.search_catalog(session, tenant.id, "muffin")) == {
        "Blueberry Muffin - Blueberry Muffin"
    }


async def test_search_edge_cases(session, shop) -> None:
    tenant, _ = shop
    assert await catalog_repo.search_catalog(session, tenant.id, "   ") == []
    assert await catalog_repo.search_catalog(session, tenant.id, "what's on the menu") == []
    assert len(await catalog_repo.search_catalog(session, tenant.id, "a", limit=2)) == 2


# ---- browse -----------------------------------------------------------------


async def test_browse_everything_active(session, shop) -> None:
    tenant, _ = shop
    assert names(await catalog_repo.browse_catalog(session, tenant.id)) == {
        "Classic Latte - Small",
        "Classic Latte - Large",
        "Iced Tea - Iced Tea",
        "Chocolate Cake - Slice",
        "Chocolate Cake - Whole",
        "Blueberry Muffin - Blueberry Muffin",
    }


async def test_browse_parent_category_includes_its_subtree(session, shop) -> None:
    tenant, _ = shop
    assert names(
        await catalog_repo.browse_catalog(session, tenant.id, category_name="beverages")
    ) == {
        "Classic Latte - Small",
        "Classic Latte - Large",
        "Iced Tea - Iced Tea",
    }


async def test_browse_leaf_category_and_unknown_category(session, shop) -> None:
    tenant, _ = shop
    assert names(await catalog_repo.browse_catalog(session, tenant.id, category_name="Hot")) == {
        "Classic Latte - Small",
        "Classic Latte - Large",
    }
    assert await catalog_repo.browse_catalog(session, tenant.id, category_name="electronics") == []


# ---- category tree ----------------------------------------------------------


async def test_category_tree_nests_children(session, shop) -> None:
    tenant, _ = shop
    tree = {node["name"]: node for node in await catalog_repo.get_category_tree(session, tenant.id)}
    assert set(tree) == {"Bakery", "Beverages"}
    assert {child["name"] for child in tree["Beverages"]["children"]} == {
        "Hot Drinks",
        "Cold Drinks",
    }


async def test_reparent_rejects_cycles(session, shop) -> None:
    tenant, catalog = shop
    with pytest.raises(ValueError, match="own parent"):
        await catalog_repo.reparent_category(
            session, tenant.id, catalog.beverages.id, catalog.beverages.id
        )
    with pytest.raises(ValueError, match="descendant"):
        await catalog_repo.reparent_category(
            session, tenant.id, catalog.beverages.id, catalog.hot_drinks.id
        )


async def test_reparent_moves_and_detaches(session, shop) -> None:
    tenant, catalog = shop
    moved = await catalog_repo.reparent_category(
        session, tenant.id, catalog.bakery.id, catalog.beverages.id
    )
    assert moved.parent_id == catalog.beverages.id
    detached = await catalog_repo.reparent_category(session, tenant.id, catalog.hot_drinks.id, None)
    assert detached.parent_id is None


async def test_deleting_a_category_keeps_its_products(session, shop) -> None:
    tenant, catalog = shop
    assert await catalog_repo.delete_category(session, tenant.id, catalog.bakery.id)
    await session.commit()
    product = await catalog_repo.get_product(session, tenant.id, catalog.cake_whole.product_id)
    await session.refresh(product)
    assert product.category_id is None


async def test_deleting_a_product_removes_its_variants(session, shop) -> None:
    tenant, catalog = shop
    assert await catalog_repo.delete_product(session, tenant.id, catalog.cake_whole.product_id)
    await session.commit()
    assert await catalog_repo.get_variant(session, tenant.id, catalog.cake_whole.id) is None


# ---- products / variants ----------------------------------------------------


async def test_standalone_product_gets_one_default_variant(session, shop) -> None:
    tenant, _ = shop
    product = await catalog_repo.create_product(
        session, tenant.id, name="Gift Card", variants=[{"price": Decimal("25")}]
    )
    [variant] = await catalog_repo.list_variants_for_product(session, tenant.id, product.id)
    assert variant.name == "Gift Card"
    assert variant.price == Decimal("25")
    assert variant.active


async def test_update_variant_ignores_none(session, shop) -> None:
    tenant, catalog = shop
    updated = await catalog_repo.update_variant(
        session, tenant.id, catalog.iced_tea.id, price=Decimal("3.00"), sku=None
    )
    assert updated.price == Decimal("3.00")


# ---- category attributes ----------------------------------------------------


async def test_effective_attributes_inherit_and_override_by_name(session, shop) -> None:
    tenant, catalog = shop
    await catalog_repo.replace_category_attributes(
        session,
        tenant.id,
        catalog.beverages.id,
        [
            {"name": "Size", "choices": ["Small", "Large"]},
            {"name": "Milk", "choices": ["Dairy", "Oat"]},
        ],
    )
    await catalog_repo.replace_category_attributes(
        session,
        tenant.id,
        catalog.hot_drinks.id,
        [{"name": "Size", "choices": ["Regular", "Grande"]}],
    )
    effective = {
        a.name: a.choices
        for a in await catalog_repo.get_effective_attributes(
            session, tenant.id, catalog.hot_drinks.id
        )
    }
    assert effective == {"Size": ["Regular", "Grande"], "Milk": ["Dairy", "Oat"]}

    # own attributes only, not inherited
    own = await catalog_repo.list_category_attributes(session, tenant.id, catalog.hot_drinks.id)
    assert [a.name for a in own] == ["Size"]


async def test_replace_attributes_is_full_replace(session, shop) -> None:
    tenant, catalog = shop
    await catalog_repo.replace_category_attributes(
        session, tenant.id, catalog.bakery.id, [{"name": "Size", "choices": ["S"]}]
    )
    await catalog_repo.replace_category_attributes(
        session, tenant.id, catalog.bakery.id, [{"name": "Flavour", "choices": ["Vanilla"]}]
    )
    assert [
        a.name
        for a in await catalog_repo.list_category_attributes(session, tenant.id, catalog.bakery.id)
    ] == ["Flavour"]
