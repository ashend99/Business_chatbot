"""Abuse and cost protection on POST /bot/message: burst rate limits and the
admin-set monthly message quota."""

from datetime import timedelta

import pytest
from factories import make_api_key, make_conversation, make_tenant
from fakes import ScriptedChatModel, ai_text
from sqlalchemy import select

from app.models.conversations import Message, MessageRole
from app.repos import conversations as conversations_repo
from app.services import bot_engine, rate_limit
from app.services.prompt_builder import local_now
from app.services.rate_limit import SlidingWindowLimiter
from app.services.settings_resolver import get_effective_settings


@pytest.fixture
def model(monkeypatch) -> ScriptedChatModel:
    scripted = ScriptedChatModel()
    monkeypatch.setattr(bot_engine, "_get_model", lambda name: scripted)
    return scripted


def message(text: str = "hi", user: str = "visitor-1") -> dict:
    return {"channel_type": "website_widget", "external_user_id": user, "text": text}


async def stored_user_messages(session, tenant_id) -> list[str]:
    stmt = select(Message.content).where(
        Message.tenant_id == tenant_id, Message.role == MessageRole.USER
    )
    return list((await session.execute(stmt)).scalars().all())


# ---- burst rate limits ------------------------------------------------------


async def test_per_customer_burst_limit(client, session, model, monkeypatch) -> None:
    monkeypatch.setattr(rate_limit, "per_user", SlidingWindowLimiter(2))
    tenant = await make_tenant(session)
    key = {"X-Api-Key": await make_api_key(session, tenant.id)}
    model.responses.extend([ai_text("1"), ai_text("2"), ai_text("3")])

    for text in ("a", "b"):
        assert (
            await client.post("/bot/message", json=message(text), headers=key)
        ).status_code == 200
    limited = await client.post("/bot/message", json=message("c"), headers=key)
    assert limited.status_code == 429
    assert 1 <= int(limited.headers["Retry-After"]) <= 60
    # rejected before anything was stored or the model was called
    assert sorted(await stored_user_messages(session, tenant.id)) == ["a", "b"]
    assert len(model.calls) == 2

    # another customer of the same tenant is unaffected
    other = await client.post("/bot/message", json=message("d", user="visitor-2"), headers=key)
    assert other.status_code == 200


async def test_per_tenant_burst_limit(client, session, model, monkeypatch) -> None:
    monkeypatch.setattr(rate_limit, "per_tenant", SlidingWindowLimiter(2))
    busy = await make_tenant(session)
    quiet = await make_tenant(session)
    busy_key = {"X-Api-Key": await make_api_key(session, busy.id)}
    quiet_key = {"X-Api-Key": await make_api_key(session, quiet.id)}
    model.responses.extend([ai_text("ok")] * 3)

    for user in ("u1", "u2"):
        assert (
            await client.post("/bot/message", json=message(user=user), headers=busy_key)
        ).status_code == 200
    assert (
        await client.post("/bot/message", json=message(user="u3"), headers=busy_key)
    ).status_code == 429
    assert (await client.post("/bot/message", json=message(), headers=quiet_key)).status_code == 200


# ---- monthly quota ----------------------------------------------------------


async def test_monthly_limit_silences_the_bot_but_keeps_messages(client, session, model) -> None:
    tenant = await make_tenant(session, admin={"monthly_message_limit": 2})
    key = {"X-Api-Key": await make_api_key(session, tenant.id)}
    model.responses.extend([ai_text("first"), ai_text("second")])

    assert (await client.post("/bot/message", json=message("1"), headers=key)).json()[
        "reply"
    ] == "first"
    assert (await client.post("/bot/message", json=message("2"), headers=key)).json()[
        "reply"
    ] == "second"

    over = (await client.post("/bot/message", json=message("3"), headers=key)).json()
    assert over["reply"] == ""
    assert over["actions"] == [{"type": "message_limit_reached", "lead_id": None}]
    assert len(model.calls) == 2  # no LLM call once over the limit
    assert sorted(await stored_user_messages(session, tenant.id)) == ["1", "2", "3"]


async def test_monthly_limit_counts_only_this_month(client, session, model) -> None:
    tenant = await make_tenant(session, admin={"monthly_message_limit": 1}, timezone="Asia/Colombo")
    key = {"X-Api-Key": await make_api_key(session, tenant.id)}
    conversation = await make_conversation(session, tenant.id)
    old = await conversations_repo.add_message(
        session, tenant.id, conversation.id, MessageRole.USER, "last month"
    )
    month_start = local_now(await get_effective_settings(tenant.id, session)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    old.created_at = month_start - timedelta(seconds=1)
    await session.commit()

    model.responses.append(ai_text("answered"))
    assert (await client.post("/bot/message", json=message(), headers=key)).json()[
        "reply"
    ] == "answered"


async def test_no_limit_means_unlimited(client, session, model) -> None:
    tenant = await make_tenant(session)  # monthly_message_limit defaults to None
    key = {"X-Api-Key": await make_api_key(session, tenant.id)}
    model.responses.extend([ai_text("ok")] * 3)
    for _ in range(3):
        assert (await client.post("/bot/message", json=message(), headers=key)).json()[
            "reply"
        ] == "ok"


async def test_admin_can_lift_the_limit(client, session, model) -> None:
    from factories import superadmin_headers

    tenant = await make_tenant(session, admin={"monthly_message_limit": 0})
    key = {"X-Api-Key": await make_api_key(session, tenant.id)}
    assert (await client.post("/bot/message", json=message(), headers=key)).json()["reply"] == ""

    await client.patch(
        f"/superadmin/tenants/{tenant.id}/settings",
        headers=superadmin_headers(),
        json={"monthly_message_limit": None},
    )
    model.responses.append(ai_text("back"))
    assert (await client.post("/bot/message", json=message(), headers=key)).json()[
        "reply"
    ] == "back"
