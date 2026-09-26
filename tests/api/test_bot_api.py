"""POST /bot/message: service-key auth, channel allowlist, human takeover.
Full agent conversations are in tests/agent/."""

import pytest
from factories import make_api_key, make_tenant
from fakes import ScriptedChatModel, ai_text
from sqlalchemy import select

from app.models.conversations import Message, MessageRole
from app.repos import tenants as tenants_repo
from app.services import bot_engine


@pytest.fixture
def model(monkeypatch) -> ScriptedChatModel:
    scripted = ScriptedChatModel()
    monkeypatch.setattr(bot_engine, "_get_model", lambda name: scripted)
    return scripted


def message(text: str = "hi", channel: str = "website_widget", user: str = "visitor-1") -> dict:
    return {"channel_type": channel, "external_user_id": user, "text": text}


async def test_requires_a_valid_api_secret(client, session, model) -> None:
    tenant = await make_tenant(session)
    key = await make_api_key(session, tenant.id)

    assert (await client.post("/bot/message", json=message())).status_code == 401
    assert (
        await client.post("/bot/message", json=message(), headers={"X-Api-Key": "wrong"})
    ).status_code == 401
    # a dashboard JWT is not a service key
    from factories import tenant_headers

    assert (
        await client.post("/bot/message", json=message(), headers=tenant_headers(tenant.id))
    ).status_code == 401

    model.responses.append(ai_text("Hello!"))
    ok = await client.post("/bot/message", json=message(), headers={"X-Api-Key": key})
    assert ok.status_code == 200
    assert ok.json()["reply"] == "Hello!"


async def test_revoked_key_and_suspended_tenant(client, session) -> None:
    tenant = await make_tenant(session)
    key = await make_api_key(session, tenant.id)
    [row] = await tenants_repo.list_api_keys(session, tenant.id)
    await tenants_repo.revoke_api_key(session, tenant.id, row.id)
    await session.commit()
    assert (
        await client.post("/bot/message", json=message(), headers={"X-Api-Key": key})
    ).status_code == 401

    other = await make_tenant(session, is_active=False)
    other_key = await make_api_key(session, other.id)
    assert (
        await client.post("/bot/message", json=message(), headers={"X-Api-Key": other_key})
    ).status_code == 403


async def test_channel_allowlist(client, session, model) -> None:
    tenant = await make_tenant(session, admin={"allowed_channels": ["whatsapp"]})
    key = await make_api_key(session, tenant.id)
    blocked = await client.post(
        "/bot/message", json=message(channel="website_widget"), headers={"X-Api-Key": key}
    )
    assert blocked.status_code == 403

    model.responses.append(ai_text("Hi from WhatsApp"))
    allowed = await client.post(
        "/bot/message", json=message(channel="whatsapp"), headers={"X-Api-Key": key}
    )
    assert allowed.status_code == 200
    assert (
        await client.post(
            "/bot/message", json=message(channel="carrier-pigeon"), headers={"X-Api-Key": key}
        )
    ).status_code == 422


async def test_bot_disabled_stores_the_message_and_stays_silent(client, session, model) -> None:
    tenant = await make_tenant(session, settings={"bot_enabled": False})
    key = await make_api_key(session, tenant.id)

    response = await client.post(
        "/bot/message", json=message("anyone there?"), headers={"X-Api-Key": key}
    )
    assert response.status_code == 200
    assert response.json()["reply"] == ""
    assert model.calls == []  # the agent never ran

    stored = (
        (await session.execute(select(Message).where(Message.tenant_id == tenant.id)))
        .scalars()
        .all()
    )
    assert [(m.role, m.content) for m in stored] == [(MessageRole.USER, "anyone there?")]


async def test_one_conversation_per_channel_user(client, session, model) -> None:
    tenant = await make_tenant(session)
    key = await make_api_key(session, tenant.id)
    model.responses.extend([ai_text("1"), ai_text("2"), ai_text("3")])

    first = (
        await client.post("/bot/message", json=message(user="u1"), headers={"X-Api-Key": key})
    ).json()
    second = (
        await client.post("/bot/message", json=message(user="u1"), headers={"X-Api-Key": key})
    ).json()
    other = (
        await client.post("/bot/message", json=message(user="u2"), headers={"X-Api-Key": key})
    ).json()
    assert first["conversation_id"] == second["conversation_id"] != other["conversation_id"]
