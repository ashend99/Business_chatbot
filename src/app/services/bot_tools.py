"""Per-request tool construction for the bot agent (Phase 4).

Tools are built fresh for every /bot/message call, as closures bound to this
request's (session, tenant_id, conversation_id) -- never module-level/shared,
so there's no risk of one tenant's tool instance leaking into another
tenant's agent run.
"""

import json
import uuid

from langchain_core.tools import StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import StockStatus
from app.models.conversations import ConversationChannel
from app.models.leads import LeadStatus
from app.repos import catalog as catalog_repo
from app.repos import documents as documents_repo
from app.repos import leads as leads_repo
from app.services.embeddings import embed_texts
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
    return f"{product.name} - {variant.name}: ${variant.price} ({stock})"


def build_tools(session: AsyncSession, tenant_id: uuid.UUID, conversation_id: uuid.UUID, channel_type: ConversationChannel) -> list[StructuredTool]:
    async def search_documents(query: str) -> str:
        """Search the business's knowledge base (policies, FAQs, general info) for an answer to an informational question."""
        embeddings = await embed_texts([query])
        results = await documents_repo.search_similar_chunks_with_scores(session, tenant_id, embeddings[0], k=5)
        max_distance = 1 - RAG_SIMILARITY_THRESHOLD
        relevant = [chunk for chunk, distance in results if distance <= max_distance]
        if not relevant:
            return "No relevant information was found in the knowledge base for this question."
        return "\n\n---\n\n".join(chunk.content for chunk in relevant)

    async def search_catalog(query: str) -> str:
        """Search the product/service catalog for pricing and stock information."""
        rows = await catalog_repo.search_catalog(session, tenant_id, query, limit=5)
        if not rows:
            return "No matching products or services were found in the catalog."
        return "\n".join(_format_variant_line(variant, product) for variant, product, _category in rows)

    async def create_lead(fields: dict, matched_variant_id: str | None = None) -> str:
        """Record a captured lead once a visitor has shown purchase intent and provided their contact details. `fields` should contain whatever contact/interest details were collected (e.g. name, phone, email). `matched_variant_id` is the id of the product/service variant they're interested in, if known."""
        variant_uuid = uuid.UUID(matched_variant_id) if matched_variant_id else None
        lead = await leads_repo.create_lead_from_bot(
            session,
            tenant_id,
            conversation_id=conversation_id,
            matched_variant_id=variant_uuid,
            status=LeadStatus.NEW,
            fields=fields,
            source_channel=channel_type.value,
        )
        await session.commit()
        return json.dumps({"lead_id": str(lead.id)})

    return [
        StructuredTool.from_function(coroutine=search_documents, name="search_documents"),
        StructuredTool.from_function(coroutine=search_catalog, name="search_catalog"),
        StructuredTool.from_function(coroutine=create_lead, name="create_lead"),
    ]
