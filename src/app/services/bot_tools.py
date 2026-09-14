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
from typing import Literal

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
from app.services.notifications import notify_new_lead, notify_new_order
from common import PROJECT_CONFIG

_agent_config = PROJECT_CONFIG.get("agent", {})
RAG_SIMILARITY_THRESHOLD = _agent_config.get("rag_similarity_threshold", 0.25)


class OrderItemInput(BaseModel):
    variant_id: str = Field(description="The variant_id shown in a prior search_catalog result.")
    quantity: int = Field(ge=1, description="How many of this item the customer wants.")


def _format_order_summary(order: Order) -> str:
    lines = [
        f"{item['quantity']}x {item['product_name']}"
        + (f" ({item['variant_label']})" if item.get("variant_label") else "")
        + f" - ${item['unit_price']} each = ${item['line_total']}"
        for item in order.items
    ]
    parts = ["\n".join(lines), f"Total: ${order.total}"]
    if order.fulfillment:
        parts.append(f"Fulfillment: {order.fulfillment}")
    if order.notes:
        parts.append(f"Notes: {order.notes}")
    return "\n".join(p for p in parts if p)


def _format_variant_line(variant, product) -> str:
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
    return f"{product.name} - {variant.name}: ${variant.price} ({stock}) [variant_id: {variant.id}]"


def build_tools(tenant_id: uuid.UUID, conversation_id: uuid.UUID, channel_type: ConversationChannel) -> list[StructuredTool]:
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
        """Search the product/service catalog for pricing and stock information."""
        async with AsyncSessionLocal() as session:
            rows = await catalog_repo.search_catalog(session, tenant_id, query, limit=5)
        if not rows:
            return "No matching products or services were found in the catalog."
        return "\n".join(_format_variant_line(variant, product) for variant, product, _category in rows)

    async def create_lead(
        fields: dict, status: Literal["interested", "new"], matched_variant_id: str | None = None
    ) -> str:
        """Record or update a captured lead. Call with status="interested" as soon as a visitor shows clear purchase intent, even before you have their full contact details -- and call again with status="new" once you've collected them; this updates the same lead rather than creating a duplicate, so it's safe to call more than once per conversation as details are refined. `fields` should contain whatever contact/interest details were collected so far (e.g. name, phone, email). `matched_variant_id` is the `variant_id` shown in a prior search_catalog result for the item they're interested in, if one was found -- omit it if no specific catalog item applies."""
        variant_uuid = uuid.UUID(matched_variant_id) if matched_variant_id else None
        lead_status = LeadStatus.NEW if status == "new" else LeadStatus.INTERESTED

        async with AsyncSessionLocal() as session:
            lead, became_new = await leads_repo.create_or_update_lead_from_bot(
                session,
                tenant_id,
                conversation_id=conversation_id,
                matched_variant_id=variant_uuid,
                status=lead_status,
                fields=fields,
                source_channel=channel_type.value,
            )
            await session.commit()

            # only ever fires once per lead -- became_new is only True on
            # the specific transition into NEW, not on every call
            if became_new:
                tenant = await tenants_repo.get_tenant_by_id(session, tenant_id)
                if tenant is not None:
                    await notify_new_lead(get_email_sender(), tenant, lead)

        return json.dumps({"lead_id": str(lead.id), "status": lead.status.value})

    async def update_order(
        items: list[OrderItemInput], fulfillment: dict | None = None, notes: str | None = None
    ) -> str:
        """Set the customer's current cart to exactly these items -- always pass the *entire* cart as it should be now (not just what changed), since this replaces the previous cart rather than adding to it. Call this as soon as the customer names specific items they want, and again any time the cart changes (quantity edits, added/removed items, fulfillment details). `fulfillment` should describe how the order reaches the customer once known, e.g. {"type": "delivery", "address": "...", "needed_by": "..."} or {"type": "pickup", "time": "..."} -- omit until you know it. Prices and the total are computed from the real catalog, never invent them yourself."""
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
                )
            except orders_repo.InvalidOrderItem as exc:
                await session.rollback()
                return f"Could not update the cart: {exc}"
            await session.commit()
        return _format_order_summary(order)

    async def confirm_order() -> str:
        """Finalize the current cart as a placed order, once the customer has explicitly confirmed the items and fulfillment details are correct. Do not call this speculatively or before they've agreed. This requires their contact details already being captured via create_lead -- if it tells you something is missing, ask for that and call create_lead before trying again. You never collect or mention taking payment -- that is handled separately by the business after this."""
        async with AsyncSessionLocal() as session:
            try:
                order = await orders_repo.confirm_order(session, tenant_id, conversation_id)
            except orders_repo.NoCartToConfirm:
                await session.rollback()
                return "There's no cart to confirm yet -- add items with update_order first."
            except orders_repo.MissingRequiredContactInfo as exc:
                await session.rollback()
                missing = ", ".join(exc.missing_labels)
                return f"Can't confirm yet -- still need the customer's {missing}. Ask for it, call create_lead with it, then try confirm_order again."
            await session.commit()

            tenant = await tenants_repo.get_tenant_by_id(session, tenant_id)
            if tenant is not None:
                await notify_new_order(get_email_sender(), tenant, order)

        return f"Order confirmed.\n\n{_format_order_summary(order)}"

    return [
        StructuredTool.from_function(coroutine=search_documents, name="search_documents"),
        StructuredTool.from_function(coroutine=search_catalog, name="search_catalog"),
        StructuredTool.from_function(coroutine=create_lead, name="create_lead"),
        StructuredTool.from_function(coroutine=update_order, name="update_order"),
        StructuredTool.from_function(coroutine=confirm_order, name="confirm_order"),
    ]
