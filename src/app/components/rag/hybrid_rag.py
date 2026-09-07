"""Hybrid RAG: fuses this app's own pgvector dense search with an
on-the-fly BM25 lexical search over the same tenant's active chunks, via
Reciprocal Rank Fusion (RRF) -- catches exact-name/keyword matches (menu
items, policy terms, proper nouns) that pure embedding similarity
sometimes under-ranks, without needing a separate persistent BM25 index to
keep in sync with publish/republish/delete.
"""

import re
import uuid
from typing import Any

from langchain_openai import ChatOpenAI
from rank_bm25 import BM25Okapi
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

# Reciprocal Rank Fusion constant -- same value as ragkit's HybridRAG
# (experiments/ragkit/rag_types/hybrid_rag.py). Large enough that *whether*
# a chunk appears near the top of either ranking matters more than its
# exact position within one.
RRF_K = 60


_TOKEN_PATTERN = re.compile(r"[a-z0-9']+")

# BM25's IDF is calibrated against *this* corpus, not English in general --
# at the scale a single tenant's document set actually is (a handful of
# chunks), a generic word like "can" that happens to appear in only one
# chunk looks artificially "rare and informative" to IDF, even though it's
# just a function word repeated many times within that one chunk (e.g. an
# FAQ document's many "Can I ...?" questions). Left unfiltered, that chunk
# can outscore one with an actual keyword match. Filtering common English
# stopwords before scoring keeps BM25 focused on content words (menu items,
# proper nouns, policy terms) -- exactly what it's here for.
_STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are aren't as at be because been
    before being below between both but by can can't cannot could couldn't did didn't do
    does doesn't doing don't down during each few for from further had hadn't has hasn't
    have haven't having he he'd he'll he's her here here's hers herself him himself his how
    how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most
    mustn't my myself no nor not of off on once only or other ought our ours ourselves out
    over own same shan't she she'd she'll she's should shouldn't so some such than that
    that's the their theirs them themselves then there there's these they they'd they'll
    they're they've this those through to too under until up very was wasn't we we'd we'll
    we're we've were weren't what what's when when's where where's which while who who's
    whom why why's will with won't would wouldn't you you'd you'll you're you've your yours
    yourself yourselves
    """.split()
)


def _tokenize(text: str) -> list[str]:
    # ragkit's BM25Index tokenizer is a plain `text.lower().split()`, which
    # leaves punctuation stuck to words ("pickme?" != "pickme") and keeps
    # stopwords -- both silently undermine the keyword matches BM25 is here
    # for, so this strips punctuation (keeping apostrophes for contractions
    # like "dula's") and filters stopwords.
    tokens = _TOKEN_PATTERN.findall(text.lower())
    return [t for t in tokens if t not in _STOPWORDS]


class HybridRAG(BaseRAG):
    """
    Same ingest ("db pusher") as NaiveRAG -- chunk + embed + insert via
    this app's own pipeline; BM25 needs no ingest-time step at all, since
    it's rebuilt fresh per query (see query()). query() fuses dense
    (pgvector cosine) and sparse (BM25) rankings via RRF instead of
    dense-only search.
    """

    def __init__(self, llm_model: str = DEFAULT_LLM_MODEL):
        self.llm_model = llm_model
        self.llm = ChatOpenAI(model=llm_model, api_key=settings.openai_api_key)

    async def ingest(self, documents: list[str | Document], **kwargs: Any) -> list[DocumentChunk]:
        """Identical to NaiveRAG.ingest() -- see its docstring."""
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

        Dense side: the same pgvector cosine search NaiveRAG uses.
        Sparse side: BM25 over all of the tenant's active chunks
        (repos.documents.list_active_chunks), built fresh for this one
        query -- cheap and always correct at this app's per-tenant scale
        (tens to low hundreds of chunks), never stale. Fused via RRF.

        Embedding happens once, entirely inside this method -- callers
        never pass one in.

        Note: the returned Documents' similarity_score is an RRF score
        (roughly 0-0.033), not a cosine similarity -- not comparable to
        NaiveRAG's or to any absolute relevance threshold calibrated
        against cosine distance. Callers that need that (e.g.
        bot_tools.py's search_documents) read the `dense_distance` entry
        this method puts in each Document's metadata instead -- present
        only for chunks that actually came from the dense side, since a
        BM25-only match has no cosine distance to report.
        """
        session: AsyncSession = kwargs["session"]
        tenant_id: uuid.UUID = kwargs["tenant_id"]
        top_k = kwargs.get("top_k", 5)

        query_embedding = (await embed_texts([question]))[0]
        dense_results = await documents_repo.search_similar_chunks_with_scores(
            session, tenant_id, query_embedding, k=top_k
        )
        dense_chunks = [chunk for chunk, _distance in dense_results]
        dense_distance_by_id = {chunk.id: distance for chunk, distance in dense_results}

        all_chunks = await documents_repo.list_active_chunks(session, tenant_id)
        sparse_chunks = self._bm25_rank(question, all_chunks, top_k)

        return self._fuse(dense_chunks, sparse_chunks, dense_distance_by_id)[:top_k]

    async def query(self, question: str, **kwargs: Any) -> RAGResponse:
        top_docs = await self.retrieve(question, **kwargs)
        prompt = self.build_rag_prompt(question, top_docs)
        response = await self.llm.ainvoke(prompt)
        answer = response.content if isinstance(response.content, str) else str(response.content)
        return RAGResponse(answer=answer, sources=top_docs)

    def _bm25_rank(self, question: str, chunks: list[DocumentChunk], top_k: int) -> list[DocumentChunk]:
        if not chunks:
            return []
        tokenized = [_tokenize(c.content) for c in chunks]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(_tokenize(question))
        ranked_indices = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
        return [chunks[i] for i in ranked_indices[:top_k]]

    def _fuse(
        self,
        dense: list[DocumentChunk],
        sparse: list[DocumentChunk],
        dense_distance_by_id: dict[uuid.UUID, float],
    ) -> list[Document]:
        dense_rank = {chunk.id: rank for rank, chunk in enumerate(dense)}
        sparse_rank = {chunk.id: rank for rank, chunk in enumerate(sparse)}

        by_id: dict[uuid.UUID, DocumentChunk] = {c.id: c for c in dense}
        by_id.update({c.id: c for c in sparse})

        scored = []
        for chunk_id, chunk in by_id.items():
            d_rank = dense_rank.get(chunk_id, float("inf"))
            s_rank = sparse_rank.get(chunk_id, float("inf"))
            rrf_score = 1 / (d_rank + RRF_K) + 1 / (s_rank + RRF_K)
            metadata = {"document_id": str(chunk.document_id), "chunk_index": chunk.chunk_index}
            if chunk_id in dense_distance_by_id:
                metadata["dense_distance"] = dense_distance_by_id[chunk_id]
            scored.append(
                Document(
                    content=chunk.content,
                    metadata=metadata,
                    similarity_score=rrf_score,
                )
            )
        return sorted(scored, key=lambda d: d.similarity_score, reverse=True)

    def build_rag_prompt(self, question: str, retrieved_docs: list[Document]) -> str:
        context = "\n\n".join(f"Document {i + 1}:\n{doc.content}" for i, doc in enumerate(retrieved_docs))
        return f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
