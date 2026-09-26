"""/tenant/settings: tenant-only writes, the admin half as read-only
capabilities, and immediate effect on the bot."""

from factories import make_tenant, tenant_headers

from app.services.settings_resolver import get_effective_settings


async def test_get_settings_shows_capabilities_but_not_admin_internals(client, session) -> None:
    tenant = await make_tenant(
        session, currency_code="LKR", admin={"ordering_allowed": False, "llm_model": "gpt-4o"}
    )
    body = (await client.get("/tenant/settings", headers=tenant_headers(tenant.id))).json()
    assert body["capabilities"] == {
        "currency_code": "LKR",
        "ordering_allowed": False,
        "catalog_allowed": True,
        "documents_allowed": True,
        "leads_allowed": True,
    }
    assert body["settings"]["bot_enabled"] is True
    assert "llm_model" not in body["capabilities"]


async def test_patch_tenant_fields(client, session) -> None:
    tenant = await make_tenant(session)
    response = await client.patch(
        "/tenant/settings",
        headers=tenant_headers(tenant.id),
        json={
            "bot_name": "Sunny",
            "tone": "casual",
            "min_order_value": "12.50",
            "timezone": "Asia/Colombo",
            "notify_emails": ["ops@example.com"],
            "order_confirmation_mode": "human",
        },
    )
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert (settings["bot_name"], settings["tone"], settings["min_order_value"]) == (
        "Sunny",
        "casual",
        "12.50",
    )
    assert settings["order_confirmation_mode"] == "human"

    cleared = await client.patch(
        "/tenant/settings", headers=tenant_headers(tenant.id), json={"bot_name": None}
    )
    assert cleared.json()["settings"]["bot_name"] is None


async def test_patch_rejections(client, session) -> None:
    tenant = await make_tenant(session)
    headers = tenant_headers(tenant.id)
    # admin-only field
    assert (
        await client.patch("/tenant/settings", headers=headers, json={"currency_code": "EUR"})
    ).status_code == 422
    # non-nullable field set to null
    assert (
        await client.patch("/tenant/settings", headers=headers, json={"bot_enabled": None})
    ).status_code == 422
    # would leave no way to receive an order
    both_off = await client.patch(
        "/tenant/settings",
        headers=headers,
        json={"delivery_enabled": False, "pickup_enabled": False},
    )
    assert both_off.status_code == 422
    await client.patch("/tenant/settings", headers=headers, json={"delivery_enabled": False})
    assert (
        await client.patch("/tenant/settings", headers=headers, json={"pickup_enabled": False})
    ).status_code == 422
    assert (
        await client.patch("/tenant/settings", headers=headers, json={"timezone": "Moon/Base"})
    ).status_code == 422


async def test_tenant_cannot_switch_on_what_admin_did_not_grant(client, session) -> None:
    tenant = await make_tenant(session, admin={"ordering_allowed": False})
    await client.patch(
        "/tenant/settings", headers=tenant_headers(tenant.id), json={"ordering_enabled": True}
    )
    assert (await get_effective_settings(tenant.id)).ordering_enabled is False


async def test_patch_takes_effect_for_the_bot_immediately(client, session) -> None:
    tenant = await make_tenant(session)
    assert (await get_effective_settings(tenant.id)).bot_enabled is True  # now cached
    await client.patch(
        "/tenant/settings", headers=tenant_headers(tenant.id), json={"bot_enabled": False}
    )
    assert (await get_effective_settings(tenant.id)).bot_enabled is False
