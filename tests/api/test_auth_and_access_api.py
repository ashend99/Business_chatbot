"""Auth end to end over HTTP (onboard -> activate -> login -> use token),
plus the access rules every protected route relies on."""

import re
import uuid

import pytest
from factories import (
    make_catalog,
    make_conversation,
    make_tenant,
    superadmin_headers,
    tenant_headers,
)

from app.core.security import create_access_token
from app.repos import tenants as tenants_repo


def token_in(body: str) -> str:
    match = re.search(r"token=([\w-]+)", body) or re.search(
        r"invitation token to log in:\s*([\w-]+)", body
    )
    return match.group(1)


async def test_full_onboarding_to_dashboard_login(client, outbox) -> None:
    created = await client.post(
        "/superadmin/tenants",
        headers=superadmin_headers(),
        json={
            "name": "Corner Bakery",
            "slug": "corner",
            "email": "owner@example.com",
            "currency_code": "gbp",
        },
    )
    assert created.status_code == 201
    invite = token_in(outbox[-1].body)

    assert (
        await client.post("/auth/activate", json={"email": "owner@example.com", "token": invite})
    ).status_code == 204
    bad = await client.post("/auth/activate", json={"email": "wrong@example.com", "token": invite})
    assert bad.status_code == 400

    done = await client.post(
        "/auth/activate/set-credentials",
        json={"token": invite, "username": "corner", "password": "a-good-password"},
    )
    assert done.status_code == 204

    login = await client.post(
        "/auth/tenant/login", json={"username": "corner", "password": "a-good-password"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    settings = await client.get("/tenant/settings", headers={"Authorization": f"Bearer {token}"})
    assert settings.status_code == 200
    assert settings.json()["capabilities"]["currency_code"] == "GBP"


async def test_login_failures(client, session, outbox) -> None:
    await client.post(
        "/superadmin/tenants",
        headers=superadmin_headers(),
        json={"name": "Shop", "slug": "shop", "email": "owner@example.com", "currency_code": "USD"},
    )
    invite = token_in(outbox[-1].body)
    await client.post(
        "/auth/activate/set-credentials",
        json={"token": invite, "username": "shop", "password": "pw-12345678"},
    )

    assert (
        await client.post("/auth/tenant/login", json={"username": "shop", "password": "wrong"})
    ).status_code == 401
    assert (
        await client.post("/auth/tenant/login", json={"username": "nobody", "password": "x"})
    ).status_code == 401

    tenant = await tenants_repo.get_tenant_by_slug(session, "shop")
    await client.post(f"/superadmin/tenants/{tenant.id}/suspend", headers=superadmin_headers())
    assert (
        await client.post(
            "/auth/tenant/login", json={"username": "shop", "password": "pw-12345678"}
        )
    ).status_code == 403


async def test_duplicate_username_is_a_conflict(client, outbox) -> None:
    for slug in ("one", "two"):
        await client.post(
            "/superadmin/tenants",
            headers=superadmin_headers(),
            json={
                "name": slug,
                "slug": slug,
                "email": f"{slug}@example.com",
                "currency_code": "USD",
            },
        )
    first, second = token_in(outbox[0].body), token_in(outbox[1].body)
    ok = await client.post(
        "/auth/activate/set-credentials",
        json={"token": first, "username": "same", "password": "pw-12345678"},
    )
    assert ok.status_code == 204
    clash = await client.post(
        "/auth/activate/set-credentials",
        json={"token": second, "username": "same", "password": "pw-12345678"},
    )
    assert clash.status_code == 409


async def test_password_reset_over_http(client, outbox) -> None:
    await client.post(
        "/superadmin/tenants",
        headers=superadmin_headers(),
        json={"name": "Shop", "slug": "shop", "email": "owner@example.com", "currency_code": "USD"},
    )
    await client.post(
        "/auth/activate/set-credentials",
        json={"token": token_in(outbox[-1].body), "username": "shop", "password": "old-password"},
    )

    assert (
        await client.post("/auth/request-password-reset", json={"username": "ghost"})
    ).status_code == 204
    assert (
        await client.post("/auth/request-password-reset", json={"username": "shop"})
    ).status_code == 204
    reset = token_in(outbox[-1].body)
    assert (
        await client.post("/auth/reset-password", json={"token": reset, "password": "short"})
    ).status_code == 422
    assert (
        await client.post("/auth/reset-password", json={"token": reset, "password": "new-password"})
    ).status_code == 204
    assert (
        await client.post(
            "/auth/reset-password", json={"token": reset, "password": "newer-password"}
        )
    ).status_code == 400
    assert (
        await client.post(
            "/auth/tenant/login", json={"username": "shop", "password": "new-password"}
        )
    ).status_code == 200


async def test_superadmin_login(client) -> None:
    ok = await client.post(
        "/superadmin/auth/login",
        json={"email": "superadmin@example.com", "password": "superadmin-test-password"},
    )
    assert ok.status_code == 200
    token = ok.json()["access_token"]
    assert (
        await client.get("/superadmin/tenants", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 200
    bad = await client.post(
        "/superadmin/auth/login", json={"email": "superadmin@example.com", "password": "nope"}
    )
    assert bad.status_code == 401


# ---- access control ---------------------------------------------------------


TENANT_ROUTES = [
    "/tenant/settings",
    "/tenant/leads",
    "/tenant/orders",
    "/tenant/conversations",
    "/tenant/documents",
    "/tenant/categories",
    "/tenant/products",
    "/tenant/lead-field-defs",
]


@pytest.mark.parametrize("path", TENANT_ROUTES)
async def test_tenant_routes_need_a_tenant_token(client, session, path: str) -> None:
    tenant = await make_tenant(session)
    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers={"Authorization": "Bearer garbage"})).status_code == 401
    assert (await client.get(path, headers=superadmin_headers())).status_code == 403
    assert (await client.get(path, headers=tenant_headers(tenant.id))).status_code == 200


async def test_superadmin_routes_reject_tenant_tokens(client, session) -> None:
    tenant = await make_tenant(session)
    assert (await client.get("/superadmin/tenants")).status_code == 401
    assert (
        await client.get("/superadmin/tenants", headers=tenant_headers(tenant.id))
    ).status_code == 403
    assert (
        await client.get(
            f"/superadmin/tenants/{tenant.id}/settings", headers=tenant_headers(tenant.id)
        )
    ).status_code == 403


async def test_suspended_tenant_token_stops_working(client, session) -> None:
    tenant = await make_tenant(session, is_active=False)
    assert (
        await client.get("/tenant/settings", headers=tenant_headers(tenant.id))
    ).status_code == 403


async def test_expired_token_is_rejected(client, session) -> None:
    tenant = await make_tenant(session)
    token = create_access_token({"sub": str(tenant.id), "scope": "tenant"}, expires_minutes=-1)
    assert (
        await client.get("/tenant/settings", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401


async def test_cross_tenant_resources_are_not_found(client, session) -> None:
    """Tenant A asking for tenant B's ids by URL gets 404, never B's data."""
    a = await make_tenant(session, name="A")
    b = await make_tenant(session, name="B")
    b_catalog = await make_catalog(session, b.id)
    b_conversation = await make_conversation(session, b.id)

    from app.models.documents import ContentSource
    from app.models.leads import LeadStatus
    from app.repos import documents as documents_repo
    from app.repos import leads as leads_repo
    from app.repos import orders as orders_repo

    lead = (
        await leads_repo.create_or_update_lead_from_bot(
            session,
            b.id,
            conversation_id=b_conversation.id,
            matched_variant_id=None,
            status=LeadStatus.INTERESTED,
            fields={"name": "B customer"},
        )
    ).lead
    order = await orders_repo.update_order(
        session,
        b.id,
        conversation_id=b_conversation.id,
        items=[{"variant_id": b_catalog.iced_tea.id, "quantity": 1}],
    )
    doc = await documents_repo.create_document(
        session,
        tenant_id=b.id,
        title="B doc",
        content_source=ContentSource.PASTE,
        draft_content="secret",
    )
    await session.commit()

    headers = tenant_headers(a.id)
    for path in [
        f"/tenant/leads/{lead.id}",
        f"/tenant/orders/{order.id}",
        f"/tenant/conversations/{b_conversation.id}",
        f"/tenant/documents/{doc.id}",
        f"/tenant/categories/{b_catalog.bakery.id}",
        f"/tenant/products/{b_catalog.iced_tea.product_id}",
    ]:
        assert (await client.get(path, headers=headers)).status_code == 404, path

    assert (
        await client.patch(f"/tenant/leads/{lead.id}", headers=headers, json={"notes": "x"})
    ).status_code == 404
    assert (
        await client.patch(
            f"/tenant/orders/{order.id}", headers=headers, json={"status": "cancelled"}
        )
    ).status_code == 404
    assert (await client.delete(f"/tenant/documents/{doc.id}", headers=headers)).status_code == 404
    assert (
        await client.delete(f"/tenant/products/{b_catalog.iced_tea.product_id}", headers=headers)
    ).status_code == 404
    listed = (
        await client.get("/tenant/catalog/search", params={"q": "tea"}, headers=headers)
    ).json()
    assert listed == []
    assert (await client.get(f"/tenant/leads/{uuid.uuid4()}", headers=headers)).status_code == 404
