"""/superadmin: tenant management, admin settings and api_secret keys."""

import uuid

from factories import make_tenant, superadmin_headers

H = superadmin_headers


async def create(client, slug: str = "shop", **extra):
    body = {
        "name": f"{slug} name",
        "slug": slug,
        "email": f"{slug}@example.com",
        "currency_code": "USD",
        **extra,
    }
    return await client.post("/superadmin/tenants", headers=H(), json=body)


async def test_create_tenant_with_admin_settings(client) -> None:
    response = await create(
        client,
        timezone="Asia/Colombo",
        admin_settings={
            "currency_code": "EUR",
            "leads_allowed": False,
            "allowed_channels": ["whatsapp"],
        },
    )
    assert response.status_code == 201
    tenant_id = response.json()["id"]

    settings = (await client.get(f"/superadmin/tenants/{tenant_id}/settings", headers=H())).json()
    # the top-level currency wins over one inside admin_settings
    assert settings["currency_code"] == "USD"
    assert settings["leads_allowed"] is False
    assert settings["allowed_channels"] == ["whatsapp"]


async def test_create_validation_and_conflicts(client) -> None:
    assert (await create(client)).status_code == 201
    assert (await create(client)).status_code == 409  # same slug
    assert (await create(client, slug="other", currency_code="EURO")).status_code == 422
    assert (
        await create(client, slug="other2", admin_settings={"bot_name": "x"})
    ).status_code == 422


async def test_list_get_update_suspend_reactivate(client) -> None:
    ids = [(await create(client, slug=s)).json()["id"] for s in ("alpha", "beta", "gamma")]

    listed = (
        await client.get("/superadmin/tenants", params={"search": "beta"}, headers=H())
    ).json()
    assert [t["slug"] for t in listed["items"]] == ["beta"] and listed["total"] == 1
    page = (
        await client.get("/superadmin/tenants", params={"page": 2, "page_size": 2}, headers=H())
    ).json()
    assert len(page["items"]) == 1 and page["total"] == 3

    detail = (await client.get(f"/superadmin/tenants/{ids[0]}", headers=H())).json()
    assert detail["activated"] is False and detail["admin_username"] is None
    assert (await client.get(f"/superadmin/tenants/{uuid.uuid4()}", headers=H())).status_code == 404

    patched = await client.patch(
        f"/superadmin/tenants/{ids[0]}", headers=H(), json={"contact_person": "Pat"}
    )
    assert patched.json()["contact_person"] == "Pat"
    clash = await client.patch(
        f"/superadmin/tenants/{ids[0]}", headers=H(), json={"email": "beta@example.com"}
    )
    assert clash.status_code == 409

    assert (await client.post(f"/superadmin/tenants/{ids[1]}/suspend", headers=H())).json()[
        "is_active"
    ] is False
    inactive = (
        await client.get("/superadmin/tenants", params={"is_active": False}, headers=H())
    ).json()
    assert [t["id"] for t in inactive["items"]] == [ids[1]]
    assert (await client.post(f"/superadmin/tenants/{ids[1]}/reactivate", headers=H())).json()[
        "is_active"
    ] is True
    assert (
        await client.post(f"/superadmin/tenants/{uuid.uuid4()}/suspend", headers=H())
    ).status_code == 404


async def test_resend_invite(client, outbox) -> None:
    tenant_id = (await create(client)).json()["id"]
    outbox.clear()
    assert (
        await client.post(f"/superadmin/tenants/{tenant_id}/resend-invite", headers=H())
    ).status_code == 204
    assert len(outbox) == 1
    await client.post(f"/superadmin/tenants/{tenant_id}/suspend", headers=H())
    assert (
        await client.post(f"/superadmin/tenants/{tenant_id}/resend-invite", headers=H())
    ).status_code == 409
    assert (
        await client.post(f"/superadmin/tenants/{uuid.uuid4()}/resend-invite", headers=H())
    ).status_code == 404


async def test_admin_settings_patch(client, session) -> None:
    tenant = await make_tenant(session)
    url = f"/superadmin/tenants/{tenant.id}/settings"

    patched = await client.patch(
        url, headers=H(), json={"currency_code": "lkr", "llm_model": "gpt-4o", "max_documents": 5}
    )
    assert patched.status_code == 200
    assert (patched.json()["currency_code"], patched.json()["llm_model"]) == ("LKR", "gpt-4o")

    cleared = await client.patch(url, headers=H(), json={"llm_model": None})
    assert cleared.json()["llm_model"] is None
    assert (
        await client.patch(url, headers=H(), json={"ordering_allowed": None})
    ).status_code == 422
    assert (await client.patch(url, headers=H(), json={"bot_name": "x"})).status_code == 422
    assert (
        await client.patch(url, headers=H(), json={"allowed_channels": ["sms"]})
    ).status_code == 422
    assert (
        await client.get(f"/superadmin/tenants/{uuid.uuid4()}/settings", headers=H())
    ).status_code == 404


async def test_admin_settings_change_reaches_the_bot_immediately(client, session) -> None:
    from app.services.settings_resolver import get_effective_settings

    tenant = await make_tenant(session)
    assert (await get_effective_settings(tenant.id)).currency_code == "USD"  # now cached
    await client.patch(
        f"/superadmin/tenants/{tenant.id}/settings", headers=H(), json={"currency_code": "EUR"}
    )
    assert (await get_effective_settings(tenant.id)).currency_code == "EUR"


async def test_api_key_lifecycle(client, session) -> None:
    tenant = await make_tenant(session)
    base = f"/superadmin/tenants/{tenant.id}/api-keys"

    created = await client.post(base, headers=H())
    assert created.status_code == 201
    key = created.json()
    assert key["key_type"] == "api_secret" and key["secret"].startswith(key["key_prefix"])

    listed = (await client.get(base, headers=H())).json()
    assert [k["id"] for k in listed] == [key["id"]]
    assert "secret" not in listed[0]  # shown exactly once

    revoked = await client.delete(f"{base}/{key['id']}", headers=H())
    assert revoked.json()["revoked_at"] is not None
    assert (await client.delete(f"{base}/{uuid.uuid4()}", headers=H())).status_code == 404

    other = await make_tenant(session)
    assert (
        await client.delete(f"/superadmin/tenants/{other.id}/api-keys/{key['id']}", headers=H())
    ).status_code == 404
