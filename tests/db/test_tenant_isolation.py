"""Multi-tenancy is enforced only at the app layer (tenant_scope(), no RLS),
so this is the most important test group: with two fully populated tenants,
every tenant-scoped read and write must see only its own tenant's rows --
and nothing at all for a suspended tenant."""

from dataclasses import dataclass

import pytest
from factories import Catalog, make_catalog, make_conversation, make_tenant
from fakes import fake_embedding

from app.models.conversations import MessageRole
from app.models.documents import ContentSource
from app.models.leads import LeadStatus
from app.models.orders import OrderStatus
from app.repos import catalog as catalog_repo
from app.repos import conversations as conversations_repo
from app.repos import documents as documents_repo
from app.repos import leads as leads_repo
from app.repos import leads_admin as leads_admin_repo
from app.repos import orders as orders_repo
from app.repos import orders_admin as orders_admin_repo
from app.repos import settings_read
from app.services.publishing import publish_document


@dataclass
class World:
    tenant_id: object
    catalog: Catalog
    conversation_id: object
    lead_id: object
    order_id: object
    document_id: object


async def populate(session, name: str) -> World:
    tenant = await make_tenant(session, name=name)
    catalog = await make_catalog(session, tenant.id)
    conversation = await make_conversation(session, tenant.id)
    await conversations_repo.add_message(
        session, tenant.id, conversation.id, MessageRole.USER, "hi"
    )
    lead = (
        await leads_repo.create_or_update_lead_from_bot(
            session,
            tenant.id,
            conversation_id=conversation.id,
            matched_variant_id=None,
            status=LeadStatus.NEW,
            fields={"name": f"{name} customer", "phone": "0700000000"},
        )
    ).lead
    order = await orders_repo.update_order(
        session,
        tenant.id,
        conversation_id=conversation.id,
        items=[{"variant_id": catalog.latte_large.id, "quantity": 1}],
        fulfillment={"type": "pickup"},
    )
    document = await documents_repo.create_document(
        session,
        tenant_id=tenant.id,
        title=f"{name} FAQ",
        content_source=ContentSource.PASTE,
        draft_content=f"The {name} refund policy is generous.",
        tags=["faq"],
    )
    await session.commit()
    await publish_document(session, tenant.id, document.id)
    return World(tenant.id, catalog, conversation.id, lead.id, order.id, document.id)


@pytest.fixture
async def worlds(session):
    return await populate(session, "Alpha"), await populate(session, "Beta")


async def test_catalog_reads_are_scoped(session, worlds) -> None:
    a, b = worlds
    a_variant_ids = {a.catalog.latte_small.id, a.catalog.latte_large.id}

    assert {
        v.id for v, _p, _c in await catalog_repo.search_catalog(session, a.tenant_id, "latte")
    } == a_variant_ids
    browsed = await catalog_repo.browse_catalog(session, a.tenant_id)
    assert {v.tenant_id for v, _p, _c in browsed} == {a.tenant_id}
    assert {c.tenant_id for c in await catalog_repo.list_categories(session, a.tenant_id)} == {
        a.tenant_id
    }
    assert {p.tenant_id for p in await catalog_repo.list_products(session, a.tenant_id)} == {
        a.tenant_id
    }
    assert await catalog_repo.get_category_tree(session, a.tenant_id)

    assert await catalog_repo.get_variant(session, a.tenant_id, b.catalog.latte_large.id) is None
    assert await catalog_repo.get_category(session, a.tenant_id, b.catalog.bakery.id) is None
    assert (
        await catalog_repo.get_product(session, a.tenant_id, b.catalog.latte_large.product_id)
        is None
    )
    assert (
        await catalog_repo.list_variants_for_product(
            session, a.tenant_id, b.catalog.latte_large.product_id
        )
        == []
    )
    assert (
        await catalog_repo.get_effective_attributes(session, a.tenant_id, b.catalog.hot_drinks.id)
        == []
    )


async def test_catalog_writes_cannot_touch_other_tenant(session, worlds) -> None:
    a, b = worlds
    assert (
        await catalog_repo.update_variant(session, a.tenant_id, b.catalog.latte_large.id, price=1)
        is None
    )
    assert (
        await catalog_repo.update_product(
            session, a.tenant_id, b.catalog.latte_large.product_id, name="x"
        )
        is None
    )
    assert (
        await catalog_repo.update_category(session, a.tenant_id, b.catalog.bakery.id, name="x")
        is None
    )
    assert (
        await catalog_repo.reparent_category(session, a.tenant_id, b.catalog.bakery.id, None)
        is None
    )
    assert not await catalog_repo.delete_variant(session, a.tenant_id, b.catalog.iced_tea.id)
    assert not await catalog_repo.delete_product(
        session, a.tenant_id, b.catalog.iced_tea.product_id
    )
    assert not await catalog_repo.delete_category(session, a.tenant_id, b.catalog.bakery.id)
    await session.commit()
    assert (
        await catalog_repo.get_variant(session, b.tenant_id, b.catalog.latte_large.id)
    ).price == b.catalog.latte_large.price


async def test_bot_cannot_order_another_tenants_variant(session, worlds) -> None:
    a, b = worlds
    with pytest.raises(orders_repo.InvalidOrderItem):
        await orders_repo.update_order(
            session,
            a.tenant_id,
            conversation_id=a.conversation_id,
            items=[{"variant_id": b.catalog.cake_whole.id, "quantity": 1}],
        )


async def test_bot_lead_upsert_never_merges_into_another_tenants_lead(session, worlds) -> None:
    a, b = worlds
    # tenant A's bot writing against B's conversation id must not find B's lead
    result = await leads_repo.create_or_update_lead_from_bot(
        session,
        a.tenant_id,
        conversation_id=b.conversation_id,
        matched_variant_id=None,
        status=LeadStatus.INTERESTED,
        fields={"name": "intruder"},
    )
    assert result.lead.id != b.lead_id
    assert result.lead.tenant_id == a.tenant_id
    await session.rollback()
    b_lead = await leads_admin_repo.get_lead(session, b.tenant_id, b.lead_id)
    assert b_lead.fields["name"] == "Beta customer"


async def test_bot_cannot_confirm_another_tenants_order(session, worlds) -> None:
    a, b = worlds
    with pytest.raises(orders_repo.NoCartToConfirm):
        await orders_repo.confirm_order(session, a.tenant_id, b.conversation_id)


async def test_leads_admin_is_scoped(session, worlds) -> None:
    a, b = worlds
    leads, total = await leads_admin_repo.list_leads(session, a.tenant_id)
    assert [lead.id for lead in leads] == [a.lead_id] and total == 1
    assert await leads_admin_repo.list_leads(session, a.tenant_id, search="Beta") == ([], 0)
    assert await leads_admin_repo.get_lead(session, a.tenant_id, b.lead_id) is None
    assert await leads_admin_repo.update_lead(session, a.tenant_id, b.lead_id, notes="x") is None
    assert {
        d.tenant_id for d in await leads_admin_repo.list_lead_field_defs(session, a.tenant_id)
    } == {a.tenant_id}


async def test_orders_admin_is_scoped(session, worlds) -> None:
    a, b = worlds
    orders, total = await orders_admin_repo.list_orders(session, a.tenant_id)
    assert [o.id for o in orders] == [a.order_id] and total == 1
    assert await orders_admin_repo.get_order(session, a.tenant_id, b.order_id) is None
    assert await orders_admin_repo.get_lead_fields(session, a.tenant_id, b.lead_id) == {}
    order, ok = await orders_admin_repo.update_order_status(
        session, a.tenant_id, b.order_id, OrderStatus.CANCELLED
    )
    assert order is None and not ok


async def test_conversations_are_scoped(session, worlds) -> None:
    a, b = worlds
    rows, total = await conversations_repo.list_conversations(session, a.tenant_id)
    assert [c.id for c, _preview in rows] == [a.conversation_id] and total == 1
    assert (
        await conversations_repo.get_conversation(session, a.tenant_id, b.conversation_id) is None
    )
    assert (
        await conversations_repo.get_recent_messages(session, a.tenant_id, b.conversation_id) == []
    )


async def test_documents_and_rag_are_scoped(session, worlds) -> None:
    a, b = worlds
    docs, total = await documents_repo.list_documents(session, a.tenant_id)
    assert [d.id for d in docs] == [a.document_id] and total == 1
    assert await documents_repo.get_document(session, a.tenant_id, b.document_id) is None
    assert (
        await documents_repo.update_document_draft(session, a.tenant_id, b.document_id, title="x")
        is None
    )
    assert not await documents_repo.delete_document(session, a.tenant_id, b.document_id)

    # B's chunk is the closer match for this query, and must still never appear
    query = fake_embedding("Beta refund policy")
    assert {
        c.tenant_id for c in await documents_repo.search_similar_chunks(session, a.tenant_id, query)
    } == {a.tenant_id}
    scored = await documents_repo.search_similar_chunks_with_scores(session, a.tenant_id, query)
    assert {c.tenant_id for c, _d in scored} == {a.tenant_id}
    assert {c.tenant_id for c in await documents_repo.list_active_chunks(session, a.tenant_id)} == {
        a.tenant_id
    }


async def test_settings_reads_are_scoped(session, worlds) -> None:
    a, _b = worlds
    assert (await settings_read.get_tenant_settings(session, a.tenant_id)).tenant_id == a.tenant_id
    assert (await settings_read.get_admin_settings(session, a.tenant_id)).tenant_id == a.tenant_id


async def test_suspended_tenant_rows_are_invisible(session, worlds) -> None:
    """tenant_scope() also requires the tenant to be active -- defense in
    depth behind the auth dependencies' suspension check."""
    a, b = worlds
    from app.repos import tenants as tenants_repo

    await tenants_repo.set_tenant_active(session, a.tenant_id, False)
    await session.commit()

    assert await catalog_repo.search_catalog(session, a.tenant_id, "latte") == []
    assert await catalog_repo.browse_catalog(session, a.tenant_id) == []
    assert await leads_admin_repo.list_leads(session, a.tenant_id) == ([], 0)
    assert await orders_admin_repo.list_orders(session, a.tenant_id) == ([], 0)
    assert await conversations_repo.list_conversations(session, a.tenant_id) == ([], 0)
    assert await documents_repo.list_active_chunks(session, a.tenant_id) == []
    assert await settings_read.get_tenant_settings(session, a.tenant_id) is None
    with pytest.raises(orders_repo.InvalidOrderItem):
        await orders_repo.update_order(
            session,
            a.tenant_id,
            conversation_id=a.conversation_id,
            items=[{"variant_id": a.catalog.iced_tea.id, "quantity": 1}],
        )
    await session.rollback()

    # the other tenant is unaffected
    assert len(await catalog_repo.search_catalog(session, b.tenant_id, "latte")) == 2
