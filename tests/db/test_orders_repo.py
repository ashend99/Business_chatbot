"""repos/orders.py: server-side pricing and every server-side rule that
gates confirm_order (the agent is never trusted to have checked these)."""

import uuid
from decimal import Decimal

import pytest
from factories import make_catalog, make_conversation, make_tenant, set_lead_fields

from app.models.leads import LeadStatus
from app.models.orders import Order, OrderStatus
from app.repos import leads as leads_repo
from app.repos import orders as orders_repo


@pytest.fixture
async def shop(session):
    tenant = await make_tenant(session)
    catalog = await make_catalog(session, tenant.id)
    conversation = await make_conversation(session, tenant.id)
    return tenant, catalog, conversation


async def cart(session, tenant, conversation, items, **kwargs) -> Order:
    order = await orders_repo.update_order(
        session,
        tenant.id,
        conversation_id=conversation.id,
        items=[{"variant_id": v.id, "quantity": q} for v, q in items],
        **kwargs,
    )
    await session.commit()
    return order


async def rollback(session, *objects) -> None:
    """Roll back a refused confirm_order. A rollback expires every loaded
    object, and async SQLAlchemy can't lazy-reload on attribute access, so
    reload the ones the test keeps using."""
    await session.rollback()
    for obj in objects:
        await session.refresh(obj)


async def add_contact(session, tenant, conversation, **fields) -> None:
    await leads_repo.create_or_update_lead_from_bot(
        session,
        tenant.id,
        conversation_id=conversation.id,
        matched_variant_id=None,
        status=LeadStatus.NEW,
        fields=fields or {"name": "Sam", "phone": "0711111111"},
    )
    await session.commit()


# ---- update_order -----------------------------------------------------------


async def test_prices_come_from_the_catalog(session, shop) -> None:
    tenant, catalog, conversation = shop
    order = await orders_repo.update_order(
        session,
        tenant.id,
        conversation_id=conversation.id,
        # an LLM-supplied price must be ignored
        items=[
            {"variant_id": str(catalog.latte_large.id), "quantity": 2, "unit_price": "0.01"},
            {"variant_id": catalog.cake_slice.id, "quantity": 1},
        ],
        currency_code="USD",
        source_channel="website_widget",
    )
    assert order.status == OrderStatus.DRAFT
    assert order.total == Decimal("13.00")
    assert order.currency_code == "USD"
    assert order.items[0] == {
        "variant_id": str(catalog.latte_large.id),
        "product_name": "Classic Latte",
        "variant_label": "Large",
        "quantity": 2,
        "unit_price": "4.50",
        "line_total": "9.00",
    }


@pytest.mark.parametrize("bad", ["unknown", "inactive", "zero_quantity"])
async def test_invalid_items_are_rejected(session, shop, bad: str) -> None:
    tenant, catalog, conversation = shop
    item = {
        "unknown": {"variant_id": uuid.uuid4(), "quantity": 1},
        "inactive": {"variant_id": catalog.retired_item.id, "quantity": 1},
        "zero_quantity": {"variant_id": catalog.iced_tea.id, "quantity": 0},
    }[bad]
    with pytest.raises(orders_repo.InvalidOrderItem):
        await orders_repo.update_order(
            session, tenant.id, conversation_id=conversation.id, items=[item]
        )


async def test_update_is_full_replace_on_the_same_draft(session, shop) -> None:
    tenant, catalog, conversation = shop
    first = await cart(
        session,
        tenant,
        conversation,
        [(catalog.latte_small, 1)],
        fulfillment={"type": "pickup"},
        currency_code="USD",
    )
    second = await cart(
        session,
        tenant,
        conversation,
        [(catalog.iced_tea, 3)],
        notes="extra ice",
        currency_code="EUR",
    )

    assert second.id == first.id
    assert [i["product_name"] for i in second.items] == ["Iced Tea"]
    assert second.total == Decimal("8.25")
    assert second.fulfillment == {"type": "pickup"}  # omitted -> kept
    assert second.notes == "extra ice"
    assert second.currency_code == "USD"  # snapshot is never overwritten


async def test_placed_order_is_frozen_and_a_new_draft_starts(session, shop) -> None:
    tenant, catalog, conversation = shop
    await add_contact(session, tenant, conversation)
    await cart(
        session, tenant, conversation, [(catalog.cake_whole, 1)], fulfillment={"type": "pickup"}
    )
    placed = await orders_repo.confirm_order(session, tenant.id, conversation.id)
    await session.commit()

    new_draft = await cart(session, tenant, conversation, [(catalog.iced_tea, 1)])
    assert new_draft.id != placed.id
    await session.refresh(placed)
    assert placed.status == OrderStatus.PLACED
    assert placed.items[0]["product_name"] == "Chocolate Cake"


# ---- confirm_order ----------------------------------------------------------


async def test_confirm_without_a_cart(session, shop) -> None:
    tenant, _catalog, conversation = shop
    with pytest.raises(orders_repo.NoCartToConfirm):
        await orders_repo.confirm_order(session, tenant.id, conversation.id)


async def test_confirm_with_an_empty_cart(session, shop) -> None:
    tenant, _catalog, conversation = shop
    await cart(session, tenant, conversation, [])
    with pytest.raises(orders_repo.NoCartToConfirm):
        await orders_repo.confirm_order(session, tenant.id, conversation.id)


async def test_confirm_requires_the_tenants_required_contact_fields(session, shop) -> None:
    tenant, catalog, conversation = shop
    await cart(
        session, tenant, conversation, [(catalog.iced_tea, 1)], fulfillment={"type": "pickup"}
    )

    with pytest.raises(orders_repo.MissingRequiredContactInfo) as no_lead:
        await orders_repo.confirm_order(session, tenant.id, conversation.id)
    assert no_lead.value.missing_labels == ["Name", "Phone Number"]
    await rollback(session, tenant, conversation)

    await add_contact(session, tenant, conversation, name="Sam")  # phone still missing
    with pytest.raises(orders_repo.MissingRequiredContactInfo) as partial:
        await orders_repo.confirm_order(session, tenant.id, conversation.id)
    assert partial.value.missing_labels == ["Phone Number"]


async def test_required_fields_are_whatever_the_tenant_configured(session, shop) -> None:
    tenant, catalog, conversation = shop
    await set_lead_fields(session, tenant.id, [("email", True), ("name", False)])
    await cart(
        session, tenant, conversation, [(catalog.iced_tea, 1)], fulfillment={"type": "pickup"}
    )
    await add_contact(session, tenant, conversation, name="Sam", phone="0711111111")

    with pytest.raises(orders_repo.MissingRequiredContactInfo) as exc:
        await orders_repo.confirm_order(session, tenant.id, conversation.id)
    assert exc.value.missing_labels == ["Email"]


async def test_no_required_fields_means_no_contact_needed(session, shop) -> None:
    tenant, catalog, conversation = shop
    await set_lead_fields(session, tenant.id, [("name", False)])
    await cart(
        session, tenant, conversation, [(catalog.iced_tea, 1)], fulfillment={"type": "pickup"}
    )
    order = await orders_repo.confirm_order(session, tenant.id, conversation.id)
    assert order.status == OrderStatus.PLACED
    assert order.lead_id is None


async def test_confirm_requires_a_fulfillment_type(session, shop) -> None:
    tenant, catalog, conversation = shop
    await add_contact(session, tenant, conversation)
    await cart(session, tenant, conversation, [(catalog.iced_tea, 1)])
    with pytest.raises(orders_repo.MissingFulfillmentInfo):
        await orders_repo.confirm_order(session, tenant.id, conversation.id)


async def test_confirm_rejects_a_fulfillment_type_not_offered(session, shop) -> None:
    tenant, catalog, conversation = shop
    await add_contact(session, tenant, conversation)
    await cart(
        session,
        tenant,
        conversation,
        [(catalog.iced_tea, 1)],
        fulfillment={"type": "delivery", "address": "1 Road"},
    )
    with pytest.raises(orders_repo.FulfillmentTypeNotOffered) as exc:
        await orders_repo.confirm_order(
            session, tenant.id, conversation.id, offered_fulfillment_types=("pickup",)
        )
    assert exc.value.chosen == "delivery"
    assert exc.value.offered == ("pickup",)


async def test_delivery_needs_an_address(session, shop) -> None:
    tenant, catalog, conversation = shop
    await add_contact(session, tenant, conversation)
    await cart(
        session, tenant, conversation, [(catalog.iced_tea, 1)], fulfillment={"type": "delivery"}
    )
    with pytest.raises(orders_repo.MissingFulfillmentDetail) as exc:
        await orders_repo.confirm_order(session, tenant.id, conversation.id)
    assert exc.value.missing == ["address"]


async def test_minimum_order_value(session, shop) -> None:
    tenant, catalog, conversation = shop
    await add_contact(session, tenant, conversation)
    await cart(
        session, tenant, conversation, [(catalog.iced_tea, 1)], fulfillment={"type": "pickup"}
    )
    with pytest.raises(orders_repo.BelowMinimumOrder) as exc:
        await orders_repo.confirm_order(
            session, tenant.id, conversation.id, min_order_value=Decimal("10")
        )
    assert (exc.value.minimum, exc.value.total) == (Decimal("10"), Decimal("2.75"))
    await rollback(session, tenant, conversation)

    order = await orders_repo.confirm_order(
        session, tenant.id, conversation.id, min_order_value=Decimal("2.75")
    )
    assert order.status == OrderStatus.PLACED


async def test_successful_confirm_places_and_links_the_lead(session, shop) -> None:
    tenant, catalog, conversation = shop
    await cart(
        session,
        tenant,
        conversation,
        [(catalog.latte_small, 2)],
        fulfillment={"type": "Delivery", "address": "1 Road"},
    )
    await add_contact(session, tenant, conversation)
    order = await orders_repo.confirm_order(session, tenant.id, conversation.id)
    await session.commit()
    assert order.status == OrderStatus.PLACED
    assert order.lead_id is not None


async def test_human_confirmation_mode_submits_instead_of_placing(session, shop) -> None:
    tenant, catalog, conversation = shop
    await add_contact(session, tenant, conversation)
    await cart(
        session, tenant, conversation, [(catalog.latte_small, 1)], fulfillment={"type": "pickup"}
    )
    order = await orders_repo.confirm_order(
        session, tenant.id, conversation.id, human_confirmation=True
    )
    assert order.status == OrderStatus.PENDING_CONFIRMATION
