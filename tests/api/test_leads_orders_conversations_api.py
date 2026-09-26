"""Dashboard read/update routes for leads, orders and conversations."""

import pytest
from factories import add_messages, make_catalog, make_conversation, make_tenant, tenant_headers

from app.models.conversations import MessageRole
from app.models.leads import LeadStatus
from app.models.orders import OrderStatus
from app.repos import leads as leads_repo
from app.repos import orders as orders_repo


@pytest.fixture
async def data(session):
    """A tenant with one conversation holding a transcript, a lead and a
    placed order."""
    tenant = await make_tenant(session)
    catalog = await make_catalog(session, tenant.id)
    conversation = await make_conversation(session, tenant.id, external_user_id="visitor-42")
    await add_messages(
        session,
        tenant.id,
        conversation.id,
        [(MessageRole.USER, "I want a cake"), (MessageRole.ASSISTANT, "Sure!")],
    )
    lead = (
        await leads_repo.create_or_update_lead_from_bot(
            session,
            tenant.id,
            conversation_id=conversation.id,
            matched_variant_id=catalog.cake_whole.id,
            status=LeadStatus.NEW,
            fields={"name": "Sam", "phone": "071"},
        )
    ).lead
    await orders_repo.update_order(
        session,
        tenant.id,
        conversation_id=conversation.id,
        items=[{"variant_id": catalog.cake_whole.id, "quantity": 1}],
        fulfillment={"type": "pickup"},
        currency_code="USD",
    )
    order = await orders_repo.confirm_order(session, tenant.id, conversation.id)
    await session.commit()
    return tenant_headers(tenant.id), conversation, lead, order


async def test_leads_list_detail_and_update(client, data) -> None:
    h, _conversation, lead, _order = data
    listed = (await client.get("/tenant/leads", params={"status": "new"}, headers=h)).json()
    assert [item["id"] for item in listed["items"]] == [str(lead.id)] and listed["total"] == 1
    assert (await client.get("/tenant/leads", params={"search": "nobody"}, headers=h)).json()[
        "total"
    ] == 0

    detail = (await client.get(f"/tenant/leads/{lead.id}", headers=h)).json()
    assert detail["fields"] == {"name": "Sam", "phone": "071"}
    assert [(m["role"], m["content"]) for m in detail["transcript"]] == [
        ("user", "I want a cake"),
        ("assistant", "Sure!"),
    ]

    updated = await client.patch(
        f"/tenant/leads/{lead.id}",
        headers=h,
        # `fields` is bot-write-only: not part of LeadUpdate, so it's ignored
        json={
            "status": "converted",
            "deal_value": "30.00",
            "notes": "Paid",
            "fields": {"name": "Hacked"},
        },
    )
    body = updated.json()
    assert (body["status"], body["deal_value"], body["notes"]) == ("converted", "30.00", "Paid")
    assert body["fields"]["name"] == "Sam"


async def test_lead_field_defs(client, data) -> None:
    h, *_ = data
    assert [
        d["field_key"] for d in (await client.get("/tenant/lead-field-defs", headers=h)).json()
    ] == ["name", "phone", "email"]
    replaced = await client.put(
        "/tenant/lead-field-defs",
        headers=h,
        json={
            "field_defs": [
                {"field_key": "company", "label": "Company", "required": True, "field_type": "text"}
            ]
        },
    )
    assert [(d["field_key"], d["required"]) for d in replaced.json()] == [("company", True)]


async def test_orders_list_detail_and_transitions(client, data) -> None:
    h, _conversation, lead, order = data
    listed = (await client.get("/tenant/orders", params={"status": "placed"}, headers=h)).json()
    assert [o["id"] for o in listed["items"]] == [str(order.id)]
    assert listed["items"][0]["currency_code"] == "USD"

    detail = (await client.get(f"/tenant/orders/{order.id}", headers=h)).json()
    assert detail["lead_id"] == str(lead.id)
    assert detail["lead_fields"] == {"name": "Sam", "phone": "071"}
    assert len(detail["transcript"]) == 2
    assert detail["total"] == "30.00"

    # staff can never move an order back into a bot-owned state
    back = await client.patch(f"/tenant/orders/{order.id}", headers=h, json={"status": "draft"})
    assert back.status_code == 400
    done = await client.patch(f"/tenant/orders/{order.id}", headers=h, json={"status": "completed"})
    assert done.json()["status"] == OrderStatus.COMPLETED.value
    again = await client.patch(
        f"/tenant/orders/{order.id}", headers=h, json={"status": "cancelled"}
    )
    assert again.status_code == 400


async def test_conversations_list_and_detail(client, data) -> None:
    h, conversation, *_ = data
    listed = (await client.get("/tenant/conversations", headers=h)).json()
    assert listed["total"] == 1
    item = listed["items"][0]
    assert (item["external_user_id"], item["last_message_preview"]) == ("visitor-42", "Sure!")
    assert (
        await client.get("/tenant/conversations", params={"channel": "whatsapp"}, headers=h)
    ).json()["total"] == 0

    detail = (await client.get(f"/tenant/conversations/{conversation.id}", headers=h)).json()
    assert [m["content"] for m in detail["messages"]] == ["I want a cake", "Sure!"]
