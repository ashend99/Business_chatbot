"""Per-request tool construction for the bot agent (Phase 4).

Tools are built fresh for every /bot/message call, as closures bound to this
request's (tenant_id, conversation_id) -- never module-level/shared, so
there's no risk of one tenant's tool instance leaking into another tenant's
agent run.

Each tool opens its own AsyncSession (rather than sharing the request's
outer session via closure) because LangGraph's ToolNode runs multiple tool
calls from a single LLM turn *concurrently* via asyncio.gather -- a shared
AsyncSession isn't safe for concurrent use from multiple coroutines and
raises `InvalidRequestError: This session is provisioning a new connection;
concurrent operations are not permitted` the moment the agent decides to
call two tools (or the same tool twice) in one turn, which real compound
questions do trigger.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.components.rag import get_rag
from app.db.session import AsyncSessionLocal
from app.models.catalog import StockStatus
from app.models.conversations import ConversationChannel
from app.models.leads import LeadStatus
from app.models.orders import Order
from app.repos import catalog as catalog_repo
from app.repos import leads as leads_repo
from app.repos import orders as orders_repo
from app.repos import tenants as tenants_repo
from app.services.email import get_email_sender
from app.services.money import format_money
from app.services.notifications import notify_new_lead, notify_new_order
from app.services.prompt_builder import enabled_tool_names
from app.services.settings_resolver import EffectiveSettings
from common import PROJECT_CONFIG

_agent_config = PROJECT_CONFIG.get("agent", {})
RAG_SIMILARITY_THRESHOLD = _agent_config.get("rag_similarity_threshold", 0.25)


class OrderItemInput(BaseModel):
    variant_id: str = Field(description="The variant_id shown in a prior search_catalog result.")
    quantity: int = Field(ge=1, description="How many of this item the customer wants.")


_FULFILLMENT_LABELS = {"type": "Type", "address": "Address", "time": "Time", "needed_by": "Needed by"}


def _format_fulfillment(fulfillment: dict) -> str:
    # never render the raw dict -- its Python repr (e.g. "{'type':
    # 'delivery', ...}") is an internal detail that leaked straight into a
    # customer-facing reply when the pricing/confirmation guardrail fell
    # back to this tool's own text verbatim
    return ", ".join(f"{_FULFILLMENT_LABELS.get(k, k.title())}: {v}" for k, v in fulfillment.items())


def _format_order_summary(order: Order, currency_code: str) -> str:
    lines = [
        f"{item['quantity']}x {item['product_name']}"
        + (f" ({item['variant_label']})" if item.get("variant_label") else "")
        + f" - {format_money(item['unit_price'], currency_code)} each = {format_money(item['line_total'], currency_code)}"
        for item in order.items
    ]
    parts = ["\n".join(lines), f"Total: {format_money(order.total, currency_code)}"]
    if order.fulfillment:
        parts.append(f"Fulfillment: {_format_fulfillment(order.fulfillment)}")
    if order.notes:
        parts.append(f"Notes: {order.notes}")
    return "\n".join(p for p in parts if p)


def _format_variant_line(variant, product, currency_code: str) -> str:
    if variant.stock_status == StockStatus.OUT_OF_STOCK:
        stock = variant.stock_message or "out of stock"
    elif variant.stock_status == StockStatus.UNLIMITED:
        stock = "in stock"
    else:
        qty = f", {variant.stock_qty} available" if variant.stock_qty is not None else ""
        stock = f"in stock{qty}"
    # variant_id is included so create_lead can be called with
    # matched_variant_id -- without it here, the agent has no way to know
    # a variant's id at all, and that field would always end up empty
    return f"{product.name} - {variant.name}: {format_money(variant.price, currency_code)} ({stock}) [variant_id: {variant.id}]"


def _format_catalog_grouped_by_category(rows: list, currency_code: str) -> str:
    groups: dict[str, list[str]] = {}
    for variant, product, category in rows:
        groups.setdefault(category.name if category else "Other", []).append(
            _format_variant_line(variant, product, currency_code)
        )
    return "\n\n".join(f"{name}:\n" + "\n".join(lines) for name, lines in groups.items())


def build_tools(
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    channel_type: ConversationChannel,
    settings: EffectiveSettings,
) -> list[StructuredTool]:
    """Only the tools this tenant's effective settings allow -- the same
    list (prompt_builder.enabled_tool_names) the system prompt describes, so
    the prompt and the toolset can't disagree."""
    currency = settings.currency_code

    async def search_documents(query: str) -> str:
        """Search the business's knowledge base (policies, FAQs, general info) for an answer to an informational question."""
        # get_rag().retrieve() embeds the query itself, once -- no separate
        # embedding call here. Its fused/hybrid ranking score isn't on a
        # comparable scale to an absolute relevance threshold (RRF is
        # roughly 0-0.033), so the gate below reads the raw cosine
        # `dense_distance` retrieve() attaches to each Document's metadata
        # instead (present only for chunks that came from the dense side).
        async with AsyncSessionLocal() as session:
            docs = await get_rag().retrieve(query, session=session, tenant_id=tenant_id, top_k=5)
        max_distance = 1 - RAG_SIMILARITY_THRESHOLD
        is_relevant = any(
            doc.metadata.get("dense_distance") is not None and doc.metadata["dense_distance"] <= max_distance
            for doc in docs
        )
        if not is_relevant:
            return "No relevant information was found in the knowledge base for this question."
        return "\n\n---\n\n".join(doc.content for doc in docs)

    async def search_catalog(query: str) -> str:
        """Search the product/service catalog for pricing and stock information about a SPECIFIC named item (e.g. "chicken pizza", "large fried rice"). Returns nothing for open-ended questions like "what do you have" or "what's on the menu" -- use browse_catalog for those instead."""
        async with AsyncSessionLocal() as session:
            rows = await catalog_repo.search_catalog(session, tenant_id, query, limit=5)
        if not rows:
            return "No matching products or services were found in the catalog."
        return "\n".join(_format_variant_line(variant, product, currency) for variant, product, _category in rows)

    async def browse_catalog(category: str | None = None) -> str:
        """List what's available, grouped by category -- use this for open-ended questions like "what do you have", "what's on the menu", "what do you sell", or when search_catalog finds nothing for a vague request. Pass `category` to narrow to one category (e.g. "beverages", "pizza"), or omit it to list everything."""
        async with AsyncSessionLocal() as session:
            rows = await catalog_repo.browse_catalog(session, tenant_id, category_name=category)
        if not rows:
            return (
                f"No items found in the '{category}' category."
                if category
                else "The catalog is currently empty."
            )
        return _format_catalog_grouped_by_category(rows, currency)

    async def create_lead(
        fields: dict, status: Literal["interested", "new"], matched_variant_id: str | None = None
    ) -> str:
        """Record or update a captured lead. Call with status="interested" as soon as a visitor shows clear purchase intent, even before you have their full contact details -- and call again with status="new" once you've collected them; this updates the same lead rather than creating a duplicate, so it's safe to call more than once per conversation as details are refined. `fields` should contain whatever contact/interest details were collected so far (e.g. name, phone, email). `matched_variant_id` is the `variant_id` shown in a prior search_catalog result for the item they're interested in, if one was found -- omit it if no specific catalog item applies."""
        variant_uuid = uuid.UUID(matched_variant_id) if matched_variant_id else None
        lead_status = LeadStatus.NEW if status == "new" else LeadStatus.INTERESTED

        async with AsyncSessionLocal() as session:
            result = await leads_repo.create_or_update_lead_from_bot(
                session,
                tenant_id,
                conversation_id=conversation_id,
                matched_variant_id=variant_uuid,
                status=lead_status,
                fields=fields,
                source_channel=channel_type.value,
            )
            lead = result.lead
            await session.commit()

            # only ever fires once per lead -- became_new is only True on
            # the specific transition into NEW, not on every call
            if result.became_new:
                tenant = await tenants_repo.get_tenant_by_id(session, tenant_id)
                if tenant is not None:
                    await notify_new_lead(get_email_sender(), tenant, lead, settings)

        response: dict = {"lead_id": str(lead.id), "status": lead.status.value}
        if result.missing_required:
            # the lead was NOT marked "new" -- tell the agent what to ask for
            # so it collects it instead of assuming the lead is complete
            response["missing_fields"] = result.missing_required
            response["note"] = (
                "Lead kept as 'interested': still need "
                + ", ".join(result.missing_required)
                + ". Ask the customer for it, then call create_lead again with status='new'."
            )
        return json.dumps(response)

    async def update_order(
        items: list[OrderItemInput], fulfillment: dict | None = None, notes: str | None = None
    ) -> str:
        """Set the customer's current cart to exactly these items -- always pass the *entire* cart as it should be now (not just what changed), since this replaces the previous cart rather than adding to it. Call this as soon as the customer names specific items they want, and again any time the cart changes (quantity edits, added/removed items, fulfillment details). `fulfillment` should describe how the order reaches the customer once known, e.g. {"type": "delivery", "address": "...", "needed_by": "..."} or {"type": "pickup", "time": "..."} -- omit until you know it. `notes` is for special instructions (or a price request you're passing along, if your instructions say so). Prices and the total are computed from the real catalog, never invent them yourself."""
        chosen_type = str((fulfillment or {}).get("type") or "").lower()
        if chosen_type and chosen_type not in settings.fulfillment_types:
            # reject up front rather than storing an order this business
            # can't fulfil that way (confirm_order enforces it too)
            offered = " or ".join(settings.fulfillment_types) or "neither"
            return f"Not saved: this business does not offer {chosen_type}. Available: {offered}. Tell the customer, and only continue with an option that is available."
        async with AsyncSessionLocal() as session:
            try:
                order = await orders_repo.update_order(
                    session,
                    tenant_id,
                    conversation_id=conversation_id,
                    items=[item.model_dump() for item in items],
                    fulfillment=fulfillment,
                    notes=notes,
                    source_channel=channel_type.value,
                    currency_code=currency,
                )
            except orders_repo.InvalidOrderItem as exc:
                await session.rollback()
                return f"Could not update the cart: {exc}"
            await session.commit()
        return _format_order_summary(order, currency)

    async def confirm_order() -> str:
        """Finalize the current cart, once the customer has explicitly confirmed the items and fulfillment details are correct. Do not call this speculatively or before they've agreed. It requires their contact details already captured via create_lead and a delivery/pickup choice already set via update_order -- if it tells you something is missing, get that first and try again. You never collect or mention taking payment -- that is handled separately by the business after this."""
        async with AsyncSessionLocal() as session:
            try:
                order = await orders_repo.confirm_order(
                    session,
                    tenant_id,
                    conversation_id,
                    offered_fulfillment_types=settings.fulfillment_types,
                    min_order_value=settings.min_order_value,
                    human_confirmation=settings.human_confirmation,
                )
            except orders_repo.NoCartToConfirm:
                await session.rollback()
                return "There's no cart to confirm yet -- add items with update_order first."
            except orders_repo.MissingRequiredContactInfo as exc:
                await session.rollback()
                missing = ", ".join(exc.missing_labels)
                return f"Can't confirm yet -- still need the customer's {missing}. Ask for it, call create_lead with it, then try confirm_order again."
            except orders_repo.MissingFulfillmentInfo:
                await session.rollback()
                offered = " or ".join(settings.fulfillment_types) or "neither"
                return f"Can't confirm yet -- ask the customer how they want to receive it ({offered}) and any detail it needs (address for delivery, time for pickup), call update_order with that, then try confirm_order again."
            except orders_repo.FulfillmentTypeNotOffered as exc:
                await session.rollback()
                offered = " or ".join(exc.offered) or "neither"
                return f"Can't confirm -- this business does not offer {exc.chosen}. Available: {offered}. Tell the customer, and if there's an alternative, update_order with that fulfillment type."
            except orders_repo.MissingFulfillmentDetail as exc:
                await session.rollback()
                return f"Can't confirm yet -- still need the {', '.join(exc.missing)} for this order. Ask the customer, call update_order with it, then try confirm_order again."
            except orders_repo.BelowMinimumOrder as exc:
                await session.rollback()
                shortfall = format_money(exc.minimum - exc.total, currency)
                return f"Can't confirm -- the minimum order is {format_money(exc.minimum, currency)} and this cart is {format_money(exc.total, currency)}. The customer needs to add {shortfall} more; tell them and offer to add items."
            await session.commit()

            tenant = await tenants_repo.get_tenant_by_id(session, tenant_id)
            if tenant is not None:
                await notify_new_order(get_email_sender(), tenant, order, settings)

        if settings.human_confirmation:
            return f"Order submitted for the business to confirm.\n\n{_format_order_summary(order, currency)}"
        return f"Order confirmed.\n\n{_format_order_summary(order, currency)}"

    available: dict[str, Callable[..., Awaitable[Any]]] = {
        "search_documents": search_documents,
        "search_catalog": search_catalog,
        "browse_catalog": browse_catalog,
        "create_lead": create_lead,
        "update_order": update_order,
        "confirm_order": confirm_order,
    }
    return [
        StructuredTool.from_function(coroutine=available[name], name=name) for name in enabled_tool_names(settings)
    ]
