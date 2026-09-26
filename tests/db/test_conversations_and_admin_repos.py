"""Conversation transcript repo, and the dashboard-side leads/orders repos
(filters, pagination, staff-allowed order transitions)."""

from datetime import UTC, datetime, timedelta

import pytest
from factories import add_messages, make_catalog, make_conversation, make_tenant

from app.models.conversations import ConversationChannel, MessageRole
from app.models.leads import LeadFieldType, LeadStatus
from app.models.orders import OrderStatus
from app.repos import conversations as conversations_repo
from app.repos import leads as leads_repo
from app.repos import leads_admin as leads_admin_repo
from app.repos import orders as orders_repo
from app.repos import orders_admin as orders_admin_repo

# ---- conversations ----------------------------------------------------------


async def test_conversation_is_unique_per_channel_and_user(session) -> None:
    tenant = await make_tenant(session)
    a = await conversations_repo.get_or_create_conversation(
        session, tenant.id, ConversationChannel.WEBSITE_WIDGET, "u1"
    )
    again = await conversations_repo.get_or_create_conversation(
        session, tenant.id, ConversationChannel.WEBSITE_WIDGET, "u1"
    )
    other_channel = await conversations_repo.get_or_create_conversation(
        session, tenant.id, ConversationChannel.WHATSAPP, "u1"
    )
    assert a.id == again.id
    assert other_channel.id != a.id


async def test_add_message_drops_nul_bytes(session) -> None:
    tenant = await make_tenant(session)
    conversation = await make_conversation(session, tenant.id)
    await add_messages(
        session,
        tenant.id,
        conversation.id,
        [(MessageRole.USER, "hello\x00 there"), (MessageRole.ASSISTANT, "hi!")],
    )

    messages = await conversations_repo.get_recent_messages(session, tenant.id, conversation.id)
    assert [(m.role, m.content) for m in messages] == [
        (MessageRole.USER, "hello there"),
        (MessageRole.ASSISTANT, "hi!"),
    ]


async def test_recent_messages_returns_the_last_n_oldest_first(session) -> None:
    tenant = await make_tenant(session)
    conversation = await make_conversation(session, tenant.id)
    await add_messages(
        session, tenant.id, conversation.id, [(MessageRole.USER, f"m{i}") for i in range(5)]
    )
    messages = await conversations_repo.get_recent_messages(
        session, tenant.id, conversation.id, limit=2
    )
    assert [m.content for m in messages] == ["m3", "m4"]


async def test_list_conversations_preview_filters_and_order(session) -> None:
    tenant = await make_tenant(session)
    older = await make_conversation(session, tenant.id, channel=ConversationChannel.WHATSAPP)
    newer = await make_conversation(session, tenant.id)
    await add_messages(
        session,
        tenant.id,
        older.id,
        [(MessageRole.USER, "first"), (MessageRole.ASSISTANT, "latest reply")],
    )
    older.last_message_at = datetime.now(UTC) - timedelta(hours=1)
    await conversations_repo.touch_conversation(session, newer)
    await session.commit()

    rows, total = await conversations_repo.list_conversations(session, tenant.id)
    assert total == 2
    assert [c.id for c, _ in rows] == [newer.id, older.id]
    assert dict((c.id, p) for c, p in rows) == {newer.id: None, older.id: "latest reply"}

    rows, total = await conversations_repo.list_conversations(
        session, tenant.id, channel_type=ConversationChannel.WHATSAPP
    )
    assert [c.id for c, _ in rows] == [older.id] and total == 1
    rows, total = await conversations_repo.list_conversations(
        session, tenant.id, page=2, page_size=1
    )
    assert [c.id for c, _ in rows] == [older.id] and total == 2


# ---- leads (dashboard) ------------------------------------------------------


async def make_leads(session, tenant, count: int) -> list:
    leads = []
    for i in range(count):
        conversation = await make_conversation(session, tenant.id)
        result = await leads_repo.create_or_update_lead_from_bot(
            session,
            tenant.id,
            conversation_id=conversation.id,
            matched_variant_id=None,
            status=LeadStatus.NEW if i % 2 else LeadStatus.INTERESTED,
            fields={"name": f"Customer {i}", "phone": f"07{i}"},
        )
        leads.append(result.lead)
    await session.commit()
    return leads


async def test_list_leads_filters_search_and_pagination(session) -> None:
    tenant = await make_tenant(session)
    leads = await make_leads(session, tenant, 5)

    items, total = await leads_admin_repo.list_leads(session, tenant.id, page=1, page_size=2)
    assert (len(items), total) == (2, 5)
    assert (await leads_admin_repo.list_leads(session, tenant.id, status=LeadStatus.NEW))[1] == 2
    found, total = await leads_admin_repo.list_leads(session, tenant.id, search="customer 3")
    assert [lead.id for lead in found] == [leads[3].id] and total == 1
    future = datetime.now(UTC) + timedelta(days=1)
    assert await leads_admin_repo.list_leads(session, tenant.id, created_after=future) == ([], 0)
    assert (await leads_admin_repo.list_leads(session, tenant.id, created_before=future))[1] == 5


async def test_update_lead_ignores_none(session) -> None:
    tenant = await make_tenant(session)
    [lead] = await make_leads(session, tenant, 1)
    updated = await leads_admin_repo.update_lead(
        session, tenant.id, lead.id, status=LeadStatus.CONTACTED, notes=None
    )
    assert updated.status == LeadStatus.CONTACTED
    assert updated.fields["name"] == "Customer 0"


async def test_lead_field_defs_seed_and_replace(session) -> None:
    tenant = await make_tenant(session)
    seeded = await leads_admin_repo.list_lead_field_defs(session, tenant.id)
    assert [(d.field_key, d.required) for d in seeded] == [
        ("name", True),
        ("phone", True),
        ("email", False),
    ]

    await leads_admin_repo.replace_lead_field_defs(
        session,
        tenant.id,
        [
            {
                "field_key": "company",
                "label": "Company",
                "field_type": LeadFieldType.TEXT,
                "required": True,
            }
        ],
    )
    await session.commit()
    replaced = await leads_admin_repo.list_lead_field_defs(session, tenant.id)
    assert [(d.field_key, d.sort_order) for d in replaced] == [("company", 0)]


# ---- orders (dashboard) -----------------------------------------------------


@pytest.fixture
async def order_in(session):
    """Returns an async factory making an order in the given status."""
    tenant = await make_tenant(session)
    catalog = await make_catalog(session, tenant.id)

    async def factory(status: OrderStatus):
        conversation = await make_conversation(session, tenant.id)
        order = await orders_repo.update_order(
            session,
            tenant.id,
            conversation_id=conversation.id,
            items=[{"variant_id": catalog.cake_whole.id, "quantity": 1}],
        )
        order.status = status
        await session.commit()
        return tenant, order

    return factory


ALLOWED = {
    (OrderStatus.DRAFT, OrderStatus.CANCELLED),
    (OrderStatus.PENDING_CONFIRMATION, OrderStatus.PLACED),
    (OrderStatus.PENDING_CONFIRMATION, OrderStatus.CANCELLED),
    (OrderStatus.PLACED, OrderStatus.COMPLETED),
    (OrderStatus.PLACED, OrderStatus.CANCELLED),
}


@pytest.mark.parametrize("current", list(OrderStatus))
@pytest.mark.parametrize("target", list(OrderStatus))
async def test_staff_order_transitions(
    session, order_in, current: OrderStatus, target: OrderStatus
) -> None:
    tenant, order = await order_in(current)
    updated, ok = await orders_admin_repo.update_order_status(session, tenant.id, order.id, target)
    assert ok is ((current, target) in ALLOWED)
    assert updated.status == (target if ok else current)


async def test_list_orders_and_lead_fields(session, order_in) -> None:
    tenant, placed = await order_in(OrderStatus.PLACED)
    await order_in(OrderStatus.DRAFT)

    assert (await orders_admin_repo.list_orders(session, tenant.id))[1] == 2
    items, total = await orders_admin_repo.list_orders(
        session, tenant.id, status=OrderStatus.PLACED
    )
    assert [o.id for o in items] == [placed.id] and total == 1
    assert (await orders_admin_repo.list_orders(session, tenant.id, search="chocolate"))[1] == 2
    assert (await orders_admin_repo.list_orders(session, tenant.id, search="pizza"))[1] == 0
    assert await orders_admin_repo.get_lead_fields(session, tenant.id, None) == {}

    lead = (
        await leads_repo.create_or_update_lead_from_bot(
            session,
            tenant.id,
            conversation_id=placed.conversation_id,
            matched_variant_id=None,
            status=LeadStatus.INTERESTED,
            fields={"name": "Sam"},
        )
    ).lead
    await session.commit()
    assert await orders_admin_repo.get_lead_fields(session, tenant.id, lead.id) == {"name": "Sam"}
