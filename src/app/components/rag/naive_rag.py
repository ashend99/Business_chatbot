"""Naive RAG: chunk -> embed -> store -> retrieve -> generate, using this
app's own pipeline end to end (services/chunking.py, services/embeddings.py,
repos/documents.py's pgvector-backed document_chunks table) -- there's one
Postgres+pgvector store for the whole app, not a separate vector DB per RAG
strategy.
"""

import uuid
from typing import Any

from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.components.rag.base import BaseRAG, Document, RAGResponse
from app.core.config import settings
from app.models.documents import DocumentChunk
from app.repos import documents as documents_repo
from app.services.chunking import approx_token_count, chunk_text
from app.services.embeddings import embed_texts
from common import PROJECT_CONFIG

_agent_config = PROJECT_CONFIG.get("agent", {})
DEFAULT_LLM_MODEL = _agent_config.get("model", "gpt-4o-mini")


class NaiveRAG(BaseRAG):
    """
    A naive RAG implementation: no reranking, no query rewriting, no
    correction loop -- straight embed -> cosine search -> stuff context ->
    generate. Also owns the ingest ("db pusher") side: chunk + embed +
    insert, the same steps services/publishing.py's safe-publish flow used
    to do inline.
    """

    def __init__(self, llm_model: str = DEFAULT_LLM_MODEL):
        self.llm_model = llm_model
        self.llm = ChatOpenAI(model=llm_model, api_key=settings.openai_api_key)

    async def ingest(self, documents: list[str | Document], **kwargs: Any) -> list[DocumentChunk]:
        """
        Chunk + embed `documents`' content and insert them as new
        DocumentChunk rows (always is_active=False) for one existing
        Document.

        Required kwargs: session (AsyncSession), tenant_id (uuid.UUID),
        document_id (uuid.UUID) -- the parent Document these chunks belong
        to.

        Deliberately does NOT flip the new chunks active, retire old ones,
        or touch documents.status -- that atomic swap + status transition
        is the safe-publish transaction boundary owned by
        services/publishing.py (see its module docstring), not a generic
        RAG concern. Returns the newly inserted (inactive) rows so the
        caller can do that swap.
        """
        session: AsyncSession = kwargs["session"]
        tenant_id: uuid.UUID = kwargs["tenant_id"]
        document_id: uuid.UUID = kwargs["document_id"]

        chunks: list[str] = []
        for doc in documents:
            content = doc.content if isinstance(doc, Document) else doc
            chunks.extend(chunk_text(content))

        if not chunks:
            return []

        embeddings = await embed_texts(chunks)
        return await documents_repo.insert_chunks(
            session,
            tenant_id=tenant_id,
            document_id=document_id,
            chunks=[
                {
                    "chunk_index": i,
                    "content": content,
                    "embedding": embedding,
                    "token_count": approx_token_count(content),
                }
                for i, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True))
            ],
        )

    async def retrieve(self, question: str, **kwargs: Any) -> list[Document]:
        """
        Required kwargs: session (AsyncSession), tenant_id (uuid.UUID).
        The query text is embedded with the same model that embedded the
        stored chunks (services/embeddings.py) -- retrieval only makes
        sense within one embedding space. Embedding happens once, entirely
        inside this method -- callers never pass one in.

        Each returned Document's metadata carries `dense_distance` (raw
        cosine distance, 0 = identical, 2 = opposite) alongside the usual
        `document_id`/`chunk_index` -- callers that need an absolute
        relevance gate (see bot_tools.py's search_documents) read it from
        there instead of re-embedding the question themselves.
        """
        session: AsyncSession = kwargs["session"]
        tenant_id: uuid.UUID = kwargs["tenant_id"]
        top_k = kwargs.get("top_k", 5)

        query_embedding = (await embed_texts([question]))[0]
        results = await documents_repo.search_similar_chunks_with_scores(session, tenant_id, query_embedding, k=top_k)

        # cosine distance (0 = identical, 2 = opposite) -> similarity, so
        # Document.similarity_score reads the same way everywhere (higher
        # = more relevant)
        return [
            Document(
                content=chunk.content,
                metadata={
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    "dense_distance": distance,
                },
                similarity_score=1 - distance,
            )
            for chunk, distance in results
        ]

    async def query(self, question: str, **kwargs: Any) -> RAGResponse:
        retrieved_docs = await self.retrieve(question, **kwargs)
        prompt = self.build_rag_prompt(question, retrieved_docs)
        response = await self.llm.ainvoke(prompt)
        answer = response.content if isinstance(response.content, str) else str(response.content)
        return RAGResponse(answer=answer, sources=retrieved_docs)

    def build_rag_prompt(self, question: str, retrieved_docs: list[Document]) -> str:
        context = "\n\n".join(f"Document {i + 1}:\n{doc.content}" for i, doc in enumerate(retrieved_docs))
        return f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
