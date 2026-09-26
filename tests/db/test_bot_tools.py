"""The agent's tools run against the real test database: what each returns
to the LLM (the text the guardrails later trust), what it writes, and which
notifications it sends."""

import json
import uuid

import pytest
from factories import make_catalog, make_conversation, make_tenant
from sqlalchemy import select

from app.models.conversations import ConversationChannel
from app.models.documents import ContentSource
from app.models.leads import Lead
from app.models.orders import Order, OrderStatus
from app.models.settings import OrderConfirmationMode
from app.repos import documents as documents_repo
from app.services.bot_tools import build_tools
from app.services.publishing import publish_document
from app.services.settings_resolver import get_effective_settings


@pytest.fixture
async def setup(session):
    """Returns an async factory building (tools-by-name, tenant, catalog,
    conversation) for a tenant with the given settings overrides."""

    async def build(**tenant_settings):
        tenant = await make_tenant(session, settings=tenant_settings)
        catalog = await make_catalog(session, tenant.id)
        conversation = await make_conversation(session, tenant.id)
        effective = await get_effective_settings(tenant.id, session)
        tools = build_tools(
            tenant.id, conversation.id, ConversationChannel.WEBSITE_WIDGET, effective
        )
        return {t.name: t for t in tools}, tenant, catalog, conversation

    return build


async def test_search_catalog(setup) -> None:
    tools, _tenant, catalog, _ = await setup()
    result = await tools["search_catalog"].ainvoke({"query": "large latte"})
    assert (
        result == f"Classic Latte - Large: $4.50 (in stock) [variant_id: {catalog.latte_large.id}]"
    )
    assert await tools["search_catalog"].ainvoke({"query": "pizza"}) == (
        "No matching products or services were found in the catalog."
    )


async def test_browse_catalog(setup) -> None:
    tools, *_ = await setup()
    everything = await tools["browse_catalog"].ainvoke({})
    assert "Bakery:\n" in everything and "Hot Drinks:\n" in everything
    assert "Blueberry Muffin - Blueberry Muffin: $2.50 (back tomorrow)" in everything
    assert "Retired Scone" not in everything

    beverages = await tools["browse_catalog"].ainvoke({"category": "beverages"})
    assert "Iced Tea" in beverages and "Cake" not in beverages
    assert (
        await tools["browse_catalog"].ainvoke({"category": "toys"})
        == "No items found in the 'toys' category."
    )


async def test_browse_empty_catalog(session) -> None:
    tenant = await make_tenant(session)
    conversation = await make_conversation(session, tenant.id)
    effective = await get_effective_settings(tenant.id, session)
    tools = {
        t.name: t
        for t in build_tools(
            tenant.id, conversation.id, ConversationChannel.WEBSITE_WIDGET, effective
        )
    }
    assert await tools["browse_catalog"].ainvoke({}) == "The catalog is currently empty."


async def test_create_lead_reports_missing_fields_then_notifies_once(
    setup, session, outbox
) -> None:
    tools, tenant, catalog, conversation = await setup()

    partial = json.loads(
        await tools["create_lead"].ainvoke(
            {
                "fields": {"name": "Sam"},
                "status": "new",
                "matched_variant_id": str(catalog.cake_whole.id),
            }
        )
    )
    assert partial["status"] == "interested"
    assert partial["missing_fields"] == ["Phone Number"]
    assert "Ask the customer for it" in partial["note"]
    assert outbox == []

    complete = json.loads(
        await tools["create_lead"].ainvoke({"fields": {"phone": "0711111111"}, "status": "new"})
    )
    assert complete == {"lead_id": partial["lead_id"], "status": "new"}
    json.loads(
        await tools["create_lead"].ainvoke(
            {"fields": {"email": "sam@example.com"}, "status": "new"}
        )
    )

    [mail] = outbox
    assert mail.to == tenant.email
    assert "- name: Sam" in mail.body and "- phone: 0711111111" in mail.body

    lead = (await session.execute(select(Lead).where(Lead.tenant_id == tenant.id))).scalar_one()
    assert lead.source_channel == "website_widget"
    assert lead.matched_variant_id == catalog.cake_whole.id


async def test_update_order_tool(setup) -> None:
    tools, _tenant, catalog, _ = await setup()
    summary = await tools["update_order"].ainvoke(
        {
            "items": [{"variant_id": str(catalog.latte_large.id), "quantity": 2}],
            "fulfillment": {"type": "delivery", "address": "12 Main St"},
            "notes": "extra hot",
        }
    )
    assert summary == (
        "2x Classic Latte (Large) - $4.50 each = $9.00\n"
        "Total: $9.00\n"
        "Fulfillment: Type: delivery, Address: 12 Main St\n"
        "Notes: extra hot"
    )
    bad = await tools["update_order"].ainvoke(
        {"items": [{"variant_id": str(uuid.uuid4()), "quantity": 1}]}
    )
    assert bad.startswith("Could not update the cart: no active catalog item found")


async def test_confirm_order_tool_walks_through_every_missing_piece(setup, session, outbox) -> None:
    tools, tenant, catalog, _ = await setup(min_order_value=10)
    confirm = tools["confirm_order"]

    assert (await confirm.ainvoke({})).startswith("There's no cart to confirm yet")

    await tools["update_order"].ainvoke(
        {"items": [{"variant_id": str(catalog.latte_small.id), "quantity": 1}]}
    )
    assert "still need the customer's Name, Phone Number" in await confirm.ainvoke({})

    await tools["create_lead"].ainvoke({"fields": {"name": "Sam", "phone": "071"}, "status": "new"})
    assert (
        "ask the customer how they want to receive it (delivery or pickup)"
        in await confirm.ainvoke({})
    )

    await tools["update_order"].ainvoke(
        {
            "items": [{"variant_id": str(catalog.latte_small.id), "quantity": 1}],
            "fulfillment": {"type": "delivery"},
        }
    )
    assert "still need the address" in await confirm.ainvoke({})

    await tools["update_order"].ainvoke(
        {
            "items": [{"variant_id": str(catalog.latte_small.id), "quantity": 1}],
            "fulfillment": {"type": "delivery", "address": "12 Main St"},
        }
    )
    below = await confirm.ainvoke({})
    assert "the minimum order is $10.00 and this cart is $3.50" in below
    assert "add $6.50 more" in below

    outbox.clear()
    await tools["update_order"].ainvoke(
        {
            "items": [{"variant_id": str(catalog.cake_whole.id), "quantity": 1}],
            "fulfillment": {"type": "delivery", "address": "12 Main St"},
        }
    )
    placed = await confirm.ainvoke({})
    assert placed.startswith("Order confirmed.\n\n1x Chocolate Cake (Whole) - $30.00 each")

    order = (await session.execute(select(Order).where(Order.tenant_id == tenant.id))).scalar_one()
    assert order.status == OrderStatus.PLACED
    [mail] = outbox
    assert mail.subject == "New order placed for Test Shop"
    assert "Total: $30.00" in mail.body


async def test_confirm_order_rejects_fulfillment_turned_off_after_cart_was_built(
    setup, session
) -> None:
    tools, tenant, catalog, conversation = await setup()
    await tools["create_lead"].ainvoke({"fields": {"name": "Sam", "phone": "071"}, "status": "new"})
    await tools["update_order"].ainvoke(
        {
            "items": [{"variant_id": str(catalog.iced_tea.id), "quantity": 1}],
            "fulfillment": {"type": "delivery", "address": "12 Main St"},
        }
    )
    # the tenant switches delivery off mid-conversation
    effective = await get_effective_settings(tenant.id, session)
    from dataclasses import replace

    tools = {
        t.name: t
        for t in build_tools(
            tenant.id,
            conversation.id,
            ConversationChannel.WEBSITE_WIDGET,
            replace(effective, delivery_enabled=False),
        )
    }
    result = await tools["confirm_order"].ainvoke({})
    assert result.startswith(
        "Can't confirm -- this business does not offer delivery. Available: pickup."
    )


async def test_confirm_order_in_human_mode_submits(setup, outbox) -> None:
    tools, _tenant, catalog, _ = await setup(order_confirmation_mode=OrderConfirmationMode.HUMAN)
    await tools["create_lead"].ainvoke({"fields": {"name": "Sam", "phone": "071"}, "status": "new"})
    await tools["update_order"].ainvoke(
        {
            "items": [{"variant_id": str(catalog.iced_tea.id), "quantity": 1}],
            "fulfillment": {"type": "pickup"},
        }
    )
    outbox.clear()
    assert (await tools["confirm_order"].ainvoke({})).startswith(
        "Order submitted for the business to confirm."
    )
    assert outbox[0].subject == "Order awaiting your confirmation for Test Shop"


async def test_notifications_follow_settings(setup, outbox) -> None:
    tools, *_ = await setup(notify_new_lead=False)
    await tools["create_lead"].ainvoke({"fields": {"name": "Sam", "phone": "071"}, "status": "new"})
    assert outbox == []

    tools, *_ = await setup(notify_emails=["a@example.com", "b@example.com"])
    await tools["create_lead"].ainvoke({"fields": {"name": "Sam", "phone": "071"}, "status": "new"})
    assert sorted(m.to for m in outbox) == ["a@example.com", "b@example.com"]


async def test_search_documents_relevance_gate(setup, session) -> None:
    tools, tenant, *_ = await setup()
    assert (await tools["search_documents"].ainvoke({"query": "refund policy"})).startswith(
        "No relevant information"
    )

    doc = await documents_repo.create_document(
        session,
        tenant_id=tenant.id,
        title="Refunds",
        content_source=ContentSource.PASTE,
        draft_content="Our refund policy: refunds within seven days with a receipt.",
    )
    await session.commit()
    await publish_document(session, tenant.id, doc.id)

    assert "refunds within seven days" in await tools["search_documents"].ainvoke(
        {"query": "what is your refund policy"}
    )
    assert (await tools["search_documents"].ainvoke({"query": "zebra xylophone"})).startswith(
        "No relevant information"
    )
