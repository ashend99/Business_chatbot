"""repos/leads.py: the bot's only lead write path -- upsert per conversation,
status enforcement, the advisory-lock race fix, and lead<->order linking."""

import asyncio
from decimal import Decimal

import pytest
from factories import make_catalog, make_conversation, make_tenant
from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.leads import Lead, LeadStatus
from app.models.orders import Order
from app.repos import leads as leads_repo
from app.repos import leads_admin as leads_admin_repo
from app.repos import orders as orders_repo


@pytest.fixture
async def chat(session):
    tenant = await make_tenant(session)
    conversation = await make_conversation(session, tenant.id)
    return tenant, conversation


async def upsert(session, tenant, conversation, status: LeadStatus, fields: dict, **kwargs):
    result = await leads_repo.create_or_update_lead_from_bot(
        session,
        tenant.id,
        conversation_id=conversation.id if conversation else None,
        matched_variant_id=kwargs.pop("matched_variant_id", None),
        status=status,
        fields=fields,
        **kwargs,
    )
    await session.commit()
    return result


async def lead_count(session, tenant_id) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(Lead).where(Lead.tenant_id == tenant_id)
        )
    ).scalar_one()


async def test_one_lead_per_conversation_refined_over_turns(session, chat) -> None:
    tenant, conversation = chat
    first = await upsert(
        session,
        tenant,
        conversation,
        LeadStatus.INTERESTED,
        {"interest": "cake"},
        source_channel="website_widget",
    )
    assert first.lead.status == LeadStatus.INTERESTED
    assert not first.became_new
    assert first.missing_required == []  # only checked when asking for NEW

    second = await upsert(
        session, tenant, conversation, LeadStatus.NEW, {"name": "Sam", "phone": "071"}
    )
    assert second.lead.id == first.lead.id
    assert second.lead.status == LeadStatus.NEW
    assert second.became_new
    assert second.lead.fields == {"interest": "cake", "name": "Sam", "phone": "071"}
    assert second.lead.source_channel == "website_widget"

    third = await upsert(
        session, tenant, conversation, LeadStatus.NEW, {"email": "sam@example.com"}
    )
    assert not third.became_new  # notification fires exactly once
    assert await lead_count(session, tenant.id) == 1


async def test_new_requires_required_fields_counting_earlier_values(session, chat) -> None:
    tenant, conversation = chat
    partial = await upsert(session, tenant, conversation, LeadStatus.NEW, {"name": "Sam"})
    assert partial.lead.status == LeadStatus.INTERESTED
    assert partial.missing_required == ["Phone Number"]
    assert not partial.became_new

    completed = await upsert(session, tenant, conversation, LeadStatus.NEW, {"phone": "071"})
    assert completed.lead.status == LeadStatus.NEW
    assert completed.became_new
    assert completed.missing_required == []


async def test_blank_values_do_not_satisfy_required_fields(session, chat) -> None:
    tenant, conversation = chat
    result = await upsert(
        session, tenant, conversation, LeadStatus.NEW, {"name": "Sam", "phone": ""}
    )
    assert result.lead.status == LeadStatus.INTERESTED


@pytest.mark.parametrize(
    "staff_status", [LeadStatus.CONTACTED, LeadStatus.CONVERTED, LeadStatus.LOST]
)
async def test_staff_status_is_kept_but_new_details_are_merged(session, chat, staff_status) -> None:
    tenant, conversation = chat
    created = await upsert(
        session, tenant, conversation, LeadStatus.NEW, {"name": "Sam", "phone": "071"}
    )
    await leads_admin_repo.update_lead(session, tenant.id, created.lead.id, status=staff_status)
    await session.commit()

    again = await upsert(
        session, tenant, conversation, LeadStatus.NEW, {"email": "sam@example.com"}
    )
    assert again.lead.status == staff_status
    assert again.lead.fields["email"] == "sam@example.com"
    assert not again.became_new


async def test_matched_variant_is_kept_when_later_calls_omit_it(session, chat) -> None:
    tenant, conversation = chat
    catalog = await make_catalog(session, tenant.id)
    await upsert(
        session,
        tenant,
        conversation,
        LeadStatus.INTERESTED,
        {},
        matched_variant_id=catalog.cake_whole.id,
    )
    later = await upsert(session, tenant, conversation, LeadStatus.INTERESTED, {"name": "Sam"})
    assert later.lead.matched_variant_id == catalog.cake_whole.id


async def test_leads_without_a_conversation_are_never_merged(session, chat) -> None:
    tenant, _conversation = chat
    a = await upsert(session, tenant, None, LeadStatus.INTERESTED, {"name": "A"})
    b = await upsert(session, tenant, None, LeadStatus.INTERESTED, {"name": "B"})
    assert a.lead.id != b.lead.id


async def test_concurrent_calls_for_one_conversation_create_one_lead(session, chat) -> None:
    """LangGraph runs same-turn tool calls concurrently, each in its own
    session. Without the advisory lock both would miss each other's row."""
    tenant, conversation = chat

    async def call(status: LeadStatus, fields: dict):
        async with AsyncSessionLocal() as own:
            result = await leads_repo.create_or_update_lead_from_bot(
                own,
                tenant.id,
                conversation_id=conversation.id,
                matched_variant_id=None,
                status=status,
                fields=fields,
            )
            await own.commit()
            return result

    results = await asyncio.gather(
        call(LeadStatus.INTERESTED, {"interest": "cake"}),
        call(LeadStatus.NEW, {"name": "Sam", "phone": "071"}),
        call(LeadStatus.INTERESTED, {"note": "birthday"}),
    )
    assert len({r.lead.id for r in results}) == 1
    assert await lead_count(session, tenant.id) == 1
    lead = (await session.execute(select(Lead).where(Lead.tenant_id == tenant.id))).scalar_one()
    assert lead.status == LeadStatus.NEW
    assert lead.fields == {"interest": "cake", "name": "Sam", "phone": "071", "note": "birthday"}


async def test_order_created_first_gets_linked_when_lead_arrives(session, chat) -> None:
    tenant, conversation = chat
    catalog = await make_catalog(session, tenant.id)
    order = await orders_repo.update_order(
        session,
        tenant.id,
        conversation_id=conversation.id,
        items=[{"variant_id": catalog.iced_tea.id, "quantity": 1}],
    )
    await session.commit()
    assert order.lead_id is None

    lead = (
        await upsert(session, tenant, conversation, LeadStatus.INTERESTED, {"name": "Sam"})
    ).lead
    await session.refresh(order)
    assert order.lead_id == lead.id


async def test_lead_created_first_is_linked_on_order_creation(session, chat) -> None:
    tenant, conversation = chat
    catalog = await make_catalog(session, tenant.id)
    lead = (
        await upsert(session, tenant, conversation, LeadStatus.INTERESTED, {"name": "Sam"})
    ).lead
    order = await orders_repo.update_order(
        session,
        tenant.id,
        conversation_id=conversation.id,
        items=[{"variant_id": catalog.iced_tea.id, "quantity": 2}],
    )
    assert order.lead_id == lead.id
    assert order.total == Decimal("5.50")


async def test_concurrent_lead_and_order_writes_end_up_linked(session, chat) -> None:
    tenant, conversation = chat
    catalog = await make_catalog(session, tenant.id)

    async def lead_call():
        async with AsyncSessionLocal() as own:
            await leads_repo.create_or_update_lead_from_bot(
                own,
                tenant.id,
                conversation_id=conversation.id,
                matched_variant_id=None,
                status=LeadStatus.INTERESTED,
                fields={"name": "Sam"},
            )
            await own.commit()

    async def order_call():
        async with AsyncSessionLocal() as own:
            await orders_repo.update_order(
                own,
                tenant.id,
                conversation_id=conversation.id,
                items=[{"variant_id": catalog.iced_tea.id, "quantity": 1}],
            )
            await own.commit()

    await asyncio.gather(lead_call(), order_call())
    order = (await session.execute(select(Order).where(Order.tenant_id == tenant.id))).scalar_one()
    lead = (await session.execute(select(Lead).where(Lead.tenant_id == tenant.id))).scalar_one()
    assert order.lead_id == lead.id


async def test_get_missing_required_fields(session, chat) -> None:
    tenant, conversation = chat
    assert await leads_repo.get_missing_required_fields(session, tenant.id, None) == [
        "Name",
        "Phone Number",
    ]
    lead = (
        await upsert(session, tenant, conversation, LeadStatus.INTERESTED, {"phone": "071"})
    ).lead
    assert await leads_repo.get_missing_required_fields(session, tenant.id, lead.id) == ["Name"]
