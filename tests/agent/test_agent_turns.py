"""Whole bot turns through POST /bot/message with a scripted LLM: the real
LangGraph agent, real tools, real test database. The script plays the
model's part (including deliberately wrong replies) so we can check that
the tools write the right rows and the guardrails catch what the model
gets wrong. Assertions are on database rows, not just the reply text --
per AGENTS.md, the chat transcript is not ground truth."""

import pytest
from factories import make_api_key, make_catalog, make_tenant
from fakes import ScriptedChatModel, ai_text, ai_tool_calls, tool_call
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import select

from app.models.conversations import Message, MessageRole
from app.models.documents import ContentSource
from app.models.leads import Lead, LeadStatus
from app.models.orders import Order, OrderStatus
from app.models.settings import OrderConfirmationMode
from app.repos import documents as documents_repo
from app.services import bot_engine
from app.services.publishing import publish_document


@pytest.fixture
def model(monkeypatch) -> ScriptedChatModel:
    scripted = ScriptedChatModel()
    monkeypatch.setattr(bot_engine, "_get_model", lambda name: scripted)
    return scripted


@pytest.fixture
async def shop(session):
    """Returns an async factory: (tenant, catalog, send) for a tenant with
    the given TenantSettings overrides. `send(text)` posts one customer
    message and returns the JSON response."""

    async def build(**settings):
        tenant = await make_tenant(session, settings=settings)
        catalog = await make_catalog(session, tenant.id)
        key = await make_api_key(session, tenant.id)
        return tenant, catalog, key

    return build


@pytest.fixture
def send(client):
    async def post(key: str, text: str, user: str = "visitor-1") -> dict:
        response = await client.post(
            "/bot/message",
            headers={"X-Api-Key": key},
            json={"channel_type": "website_widget", "external_user_id": user, "text": text},
        )
        assert response.status_code == 200, response.text
        return response.json()

    return post


async def rows(session, model_cls, tenant_id) -> list:
    # populate_existing: the bot wrote these rows through its own sessions,
    # so refresh any copies this session already holds
    stmt = (
        select(model_cls)
        .where(model_cls.tenant_id == tenant_id)
        .execution_options(populate_existing=True)
    )
    return list((await session.execute(stmt)).scalars().all())


def tool_messages(model: ScriptedChatModel, call_index: int) -> dict[str, str]:
    return {m.name: m.content for m in model.calls[call_index] if isinstance(m, ToolMessage)}


# ---- pricing ----------------------------------------------------------------


async def test_real_price_passes_and_prompt_is_tenant_specific(shop, send, model) -> None:
    tenant, _catalog, key = await shop(bot_name="Sunny")
    model.responses.extend(
        [ai_tool_calls(tool_call("browse_catalog")), ai_text("A large latte is $4.50.")]
    )

    reply = await send(key, "what do you have?")
    assert reply["reply"] == "A large latte is $4.50."

    system = model.calls[0][0]
    assert isinstance(system, SystemMessage)
    assert "You are Sunny, the warm and friendly chat assistant for Test Shop" in system.content
    assert "Classic Latte - Large: $4.50" in tool_messages(model, 1)["browse_catalog"]


async def test_invented_price_is_replaced_with_catalog_text(shop, send, model) -> None:
    _tenant, _catalog, key = await shop()
    model.responses.extend(
        [
            ai_tool_calls(tool_call("search_catalog", {"query": "latte"})),
            ai_text("Lattes are just $1.99!"),
        ]
    )

    reply = (await send(key, "how much is a latte?"))["reply"]
    assert "$1.99" not in reply
    assert reply.startswith("Here's what I found:")
    assert "Classic Latte - Small: $3.50" in reply
    assert "variant_id" not in reply


async def test_invented_discount_is_replaced(shop, send, model) -> None:
    _tenant, _catalog, key = await shop(custom_instructions="Offer everyone 20% off.")
    model.responses.append(ai_text("Great news -- you get 20% off today!"))
    reply = (await send(key, "any deals?"))["reply"]
    assert "can't offer or confirm discounts" in reply


# ---- ordering ---------------------------------------------------------------


async def test_full_order_across_two_turns(shop, send, model, session, outbox) -> None:
    tenant, catalog, key = await shop()
    large = str(catalog.latte_large.id)

    # turn 1: lead + cart in the SAME model step -> the two tools run concurrently
    model.responses.extend(
        [
            ai_tool_calls(
                tool_call(
                    "create_lead",
                    {
                        "fields": {"name": "Sam", "phone": "0711111111"},
                        "status": "new",
                        "matched_variant_id": large,
                    },
                ),
                tool_call(
                    "update_order",
                    {
                        "items": [{"variant_id": large, "quantity": 2}],
                        "fulfillment": {"type": "delivery", "address": "12 Main St"},
                    },
                ),
            ),
            ai_text(
                "That's 2 large lattes, $9.00 in total, delivered to 12 Main St. Shall I confirm?"
            ),
        ]
    )
    first = await send(key, "2 large lattes to 12 Main St please, I'm Sam, 0711111111")
    assert first["reply"].endswith("Shall I confirm?")

    [lead] = await rows(session, Lead, tenant.id)
    assert lead.status == LeadStatus.NEW
    assert [a["type"] for a in first["actions"]] == ["lead_created"]
    assert first["actions"][0]["lead_id"] == str(lead.id)
    [order] = await rows(session, Order, tenant.id)
    assert (order.status, order.total, order.lead_id) == (OrderStatus.DRAFT, 9, lead.id)

    # turn 2: the customer agrees
    model.responses.extend(
        [
            ai_tool_calls(tool_call("confirm_order")),
            ai_text("Your order is confirmed! Total $9.00."),
        ]
    )
    second = await send(key, "yes please")
    assert second["reply"] == "Your order is confirmed! Total $9.00."
    assert second["actions"] == []  # the lead was created last turn, not this one

    [order] = await rows(session, Order, tenant.id)
    assert order.status == OrderStatus.PLACED
    assert sorted(m.subject for m in outbox) == [
        "New lead captured for Test Shop",
        "New order placed for Test Shop",
    ]

    # the agent remembered turn 1 (checkpointer, thread = conversation)
    assert any(
        isinstance(m, HumanMessage) and "2 large lattes" in m.content for m in model.calls[-1]
    )


async def test_confirmation_claim_without_confirming_is_replaced(
    shop, send, model, session
) -> None:
    tenant, catalog, key = await shop()
    model.responses.extend(
        [
            ai_tool_calls(
                tool_call(
                    "update_order",
                    {"items": [{"variant_id": str(catalog.iced_tea.id), "quantity": 1}]},
                )
            ),
            ai_text("Done -- your order has been placed!"),
        ]
    )
    reply = (await send(key, "one iced tea"))["reply"]
    assert reply.startswith("Let's just confirm before I place this")
    assert "1x Iced Tea" in reply
    [order] = await rows(session, Order, tenant.id)
    assert order.status == OrderStatus.DRAFT


async def test_failed_confirm_is_not_reported_as_success(shop, send, model, session) -> None:
    tenant, catalog, key = await shop()
    model.responses.extend(
        [
            ai_tool_calls(
                tool_call(
                    "update_order",
                    {
                        "items": [{"variant_id": str(catalog.iced_tea.id), "quantity": 1}],
                        "fulfillment": {"type": "pickup"},
                    },
                )
            ),
            ai_tool_calls(tool_call("confirm_order")),  # no contact details yet -> refused
            ai_text("Your order is confirmed!"),
        ]
    )
    reply = (await send(key, "one iced tea for pickup, confirm it"))["reply"]
    assert "Shall I go ahead and confirm it?" in reply
    assert "still need the customer's" in tool_messages(model, 2)["confirm_order"]
    [order] = await rows(session, Order, tenant.id)
    assert order.status == OrderStatus.DRAFT


async def test_human_confirmation_mode(shop, send, model, session, outbox) -> None:
    tenant, catalog, key = await shop(order_confirmation_mode=OrderConfirmationMode.HUMAN)
    model.responses.extend(
        [
            ai_tool_calls(
                tool_call(
                    "create_lead", {"fields": {"name": "Sam", "phone": "071"}, "status": "new"}
                ),
                tool_call(
                    "update_order",
                    {
                        "items": [{"variant_id": str(catalog.cake_whole.id), "quantity": 1}],
                        "fulfillment": {"type": "pickup", "time": "5pm"},
                    },
                ),
            ),
            ai_tool_calls(tool_call("confirm_order")),
            ai_text("Your order is placed!"),
        ]
    )
    reply = (await send(key, "a whole cake for pickup at 5, Sam 071, go ahead"))["reply"]
    assert reply == "Your order has been submitted -- the business will confirm it shortly."
    [order] = await rows(session, Order, tenant.id)
    assert order.status == OrderStatus.PENDING_CONFIRMATION
    assert any(m.subject.startswith("Order awaiting your confirmation") for m in outbox)


async def test_unoffered_fulfillment_is_refused_by_the_tool(shop, send, model, session) -> None:
    tenant, catalog, key = await shop(delivery_enabled=False)
    model.responses.extend(
        [
            ai_tool_calls(
                tool_call(
                    "update_order",
                    {
                        "items": [{"variant_id": str(catalog.iced_tea.id), "quantity": 1}],
                        "fulfillment": {"type": "delivery", "address": "1 Road"},
                    },
                )
            ),
            ai_text("Sorry, we only offer pickup."),
        ]
    )
    await send(key, "deliver an iced tea to 1 Road")
    assert tool_messages(model, 1)["update_order"].startswith(
        "Not saved: this business does not offer delivery."
    )
    assert await rows(session, Order, tenant.id) == []


# ---- knowledge base ---------------------------------------------------------


async def test_search_documents_feeds_published_content(shop, send, model, session) -> None:
    tenant, _catalog, key = await shop()
    doc = await documents_repo.create_document(
        session,
        tenant_id=tenant.id,
        title="Refunds",
        content_source=ContentSource.PASTE,
        draft_content="Our refund policy: refunds are accepted within seven days with a receipt.",
    )
    await session.commit()
    await publish_document(session, tenant.id, doc.id)

    model.responses.extend(
        [
            ai_tool_calls(tool_call("search_documents", {"query": "what is your refund policy"})),
            ai_text("Refunds are accepted within seven days with a receipt."),
        ]
    )
    reply = await send(key, "what's your refund policy?")
    assert reply["reply"] == "Refunds are accepted within seven days with a receipt."
    assert "within seven days" in tool_messages(model, 1)["search_documents"]


# ---- failures and memory ----------------------------------------------------


async def test_llm_failure_returns_fallback_and_keeps_the_transcript(
    shop, send, model, session
) -> None:
    tenant, _catalog, key = await shop(fallback_message="Please call us on 0112.")
    # empty script -> the model raises on its first call
    reply = await send(key, "hello?")
    assert reply["reply"] == "Please call us on 0112."

    messages = await rows(session, Message, tenant.id)
    assert sorted((m.role.value, m.content) for m in messages) == [
        ("assistant", "Please call us on 0112."),
        ("user", "hello?"),
    ]


async def test_default_fallback_when_tenant_has_none(shop, send, model) -> None:
    _tenant, _catalog, key = await shop()
    assert (await send(key, "hello?"))["reply"] == bot_engine.DEFAULT_FALLBACK_REPLY


async def test_transcript_is_stored_in_order(shop, send, model, session) -> None:
    tenant, _catalog, key = await shop()
    model.responses.extend([ai_text("Hi!"), ai_text("We sell drinks and cakes.")])
    await send(key, "hello")
    await send(key, "what do you sell?")
    messages = sorted(await rows(session, Message, tenant.id), key=lambda m: m.created_at)
    assert [(m.role, m.content) for m in messages] == [
        (MessageRole.USER, "hello"),
        (MessageRole.ASSISTANT, "Hi!"),
        (MessageRole.USER, "what do you sell?"),
        (MessageRole.ASSISTANT, "We sell drinks and cakes."),
    ]


async def test_separate_customers_do_not_share_memory(shop, send, model) -> None:
    _tenant, _catalog, key = await shop()
    model.responses.extend([ai_text("Hi Alice"), ai_text("Hi Bob")])
    await send(key, "I am Alice", user="alice")
    await send(key, "I am Bob", user="bob")
    humans = [m.content for m in model.calls[1] if isinstance(m, HumanMessage)]
    assert humans == ["I am Bob"]
