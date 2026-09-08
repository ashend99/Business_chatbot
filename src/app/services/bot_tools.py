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

from app.components.rag import get_rag
from app.db.session import AsyncSessionLocal
from app.models.catalog import StockStatus
from app.models.conversations import ConversationChannel
from app.models.leads import LeadStatus
from app.repos import catalog as catalog_repo
from app.repos import leads as leads_repo
from app.repos import tenants as tenants_repo
from app.services.email import get_email_sender
from app.services.notifications import notify_new_lead
from common import PROJECT_CONFIG

_agent_config = PROJECT_CONFIG.get("agent", {})
RAG_SIMILARITY_THRESHOLD = _agent_config.get("rag_similarity_threshold", 0.25)


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

            # # only ever fires once per lead -- became_new is only True on
            # # the specific transition into NEW, not on every call
            # if became_new:
            #     tenant = await tenants_repo.get_tenant_by_id(session, tenant_id)
            #     if tenant is not None:
            #         await notify_new_lead(get_email_sender(), tenant, lead)

        return json.dumps({"lead_id": str(lead.id), "status": lead.status.value})

    return [
        StructuredTool.from_function(coroutine=search_documents, name="search_documents"),
        StructuredTool.from_function(coroutine=search_catalog, name="search_catalog"),
        StructuredTool.from_function(coroutine=create_lead, name="create_lead"),
    ]
