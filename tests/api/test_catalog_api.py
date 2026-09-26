"""/tenant catalog routes: categories (tree, reparent, attributes),
products, variants and search."""

import uuid

import pytest
from factories import make_tenant, tenant_headers


@pytest.fixture
async def api(client, session):
    """(client, headers) for a fresh tenant."""
    tenant = await make_tenant(session)
    return client, tenant_headers(tenant.id)


async def test_category_crud_tree_and_reparent(api) -> None:
    client, h = api
    drinks = (await client.post("/tenant/categories", headers=h, json={"name": "Drinks"})).json()
    hot = (
        await client.post(
            "/tenant/categories", headers=h, json={"name": "Hot", "parent_id": drinks["id"]}
        )
    ).json()
    assert hot["parent_id"] == drinks["id"]

    tree = (await client.get("/tenant/categories/tree", headers=h)).json()
    assert [(n["name"], [c["name"] for c in n["children"]]) for n in tree] == [("Drinks", ["Hot"])]

    renamed = await client.patch(
        f"/tenant/categories/{hot['id']}", headers=h, json={"name": "Hot Drinks"}
    )
    assert renamed.json()["name"] == "Hot Drinks"

    cycle = await client.patch(
        f"/tenant/categories/{drinks['id']}/reparent", headers=h, json={"parent_id": hot["id"]}
    )
    assert cycle.status_code == 400
    moved = await client.patch(
        f"/tenant/categories/{hot['id']}/reparent", headers=h, json={"parent_id": None}
    )
    assert moved.json()["parent_id"] is None

    assert (await client.delete(f"/tenant/categories/{hot['id']}", headers=h)).status_code == 204
    assert (await client.get(f"/tenant/categories/{hot['id']}", headers=h)).status_code == 404
    assert [c["name"] for c in (await client.get("/tenant/categories", headers=h)).json()] == [
        "Drinks"
    ]


async def test_category_attributes(api) -> None:
    client, h = api
    parent = (await client.post("/tenant/categories", headers=h, json={"name": "Cakes"})).json()
    child = (
        await client.post(
            "/tenant/categories", headers=h, json={"name": "Birthday", "parent_id": parent["id"]}
        )
    ).json()

    put = await client.put(
        f"/tenant/categories/{parent['id']}/attributes",
        headers=h,
        json={"attributes": [{"name": "Size", "choices": ["1kg", "2kg"]}]},
    )
    assert put.status_code == 200
    await client.put(
        f"/tenant/categories/{child['id']}/attributes",
        headers=h,
        json={"attributes": [{"name": "Flavour", "choices": ["Vanilla"]}]},
    )
    own = (await client.get(f"/tenant/categories/{child['id']}/attributes", headers=h)).json()
    assert [a["name"] for a in own] == ["Flavour"]
    effective = (
        await client.get(f"/tenant/categories/{child['id']}/effective-attributes", headers=h)
    ).json()
    assert sorted(a["name"] for a in effective) == ["Flavour", "Size"]

    missing = uuid.uuid4()
    assert (
        await client.get(f"/tenant/categories/{missing}/attributes", headers=h)
    ).status_code == 404
    assert (
        await client.put(
            f"/tenant/categories/{missing}/attributes", headers=h, json={"attributes": []}
        )
    ).status_code == 404


async def test_products_and_variants(api) -> None:
    client, h = api
    standalone = await client.post(
        "/tenant/products", headers=h, json={"name": "Gift Card", "price": "25.00"}
    )
    assert standalone.status_code == 201
    assert [(v["name"], v["price"]) for v in standalone.json()["variants"]] == [
        ("Gift Card", "25.00")
    ]
    assert (
        await client.post("/tenant/products", headers=h, json={"name": "No price"})
    ).status_code == 422

    product = (
        await client.post(
            "/tenant/products",
            headers=h,
            json={
                "name": "Tote Bag",
                "variants": [
                    {"name": "Red", "price": "10"},
                    {"name": "Blue", "price": "12", "attribute_values": {"Colour": "Blue"}},
                ],
            },
        )
    ).json()
    pid = product["id"]
    assert sorted(v["name"] for v in product["variants"]) == ["Blue", "Red"]

    added = (
        await client.post(
            f"/tenant/products/{pid}/variants", headers=h, json={"name": "Green", "price": "11"}
        )
    ).json()
    updated = await client.patch(
        f"/tenant/products/{pid}/variants/{added['id']}",
        headers=h,
        json={"price": "9.50", "active": False},
    )
    assert (updated.json()["price"], updated.json()["active"]) == ("9.50", False)

    # a variant addressed through the wrong product is not found
    other = standalone.json()["id"]
    assert (
        await client.patch(
            f"/tenant/products/{other}/variants/{added['id']}", headers=h, json={"price": "1"}
        )
    ).status_code == 404
    assert (
        await client.delete(f"/tenant/products/{other}/variants/{added['id']}", headers=h)
    ).status_code == 404
    assert (
        await client.delete(f"/tenant/products/{pid}/variants/{added['id']}", headers=h)
    ).status_code == 204
    assert len((await client.get(f"/tenant/products/{pid}/variants", headers=h)).json()) == 2

    renamed = await client.patch(f"/tenant/products/{pid}", headers=h, json={"name": "Canvas Tote"})
    assert renamed.json()["name"] == "Canvas Tote"
    assert (await client.get(f"/tenant/products/{pid}", headers=h)).json()["name"] == "Canvas Tote"
    assert len((await client.get("/tenant/products", headers=h)).json()) == 2

    assert (await client.delete(f"/tenant/products/{pid}", headers=h)).status_code == 204
    assert (await client.get(f"/tenant/products/{pid}", headers=h)).status_code == 404
    assert (
        await client.post(
            f"/tenant/products/{pid}/variants", headers=h, json={"name": "x", "price": "1"}
        )
    ).status_code == 404


async def test_catalog_search_endpoint(api) -> None:
    client, h = api
    category = (
        await client.post("/tenant/categories", headers=h, json={"name": "Stationery"})
    ).json()
    await client.post(
        "/tenant/products",
        headers=h,
        json={
            "name": "Notebook",
            "category_id": category["id"],
            "variants": [{"name": "A5", "price": "4"}],
        },
    )
    results = (
        await client.get("/tenant/catalog/search", params={"q": "a5 notebook"}, headers=h)
    ).json()
    assert [
        (r["product_name"], r["variant_name"], r["category_name"], r["price"]) for r in results
    ] == [("Notebook", "A5", "Stationery", "4.00")]
    assert (
        await client.get("/tenant/catalog/search", params={"q": ""}, headers=h)
    ).status_code == 422
