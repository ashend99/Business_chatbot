"""Singleton accessor for the app's active RAG implementation.

Everything that needs RAG -- services/publishing.py's ingest step today,
potentially the bot's search_documents tool later -- goes through
get_rag(), not a specific class, so the underlying strategy can be swapped
(config-driven) without touching callers.
"""

from app.components.rag.base import BaseRAG, Document, RAGResponse
from app.components.rag.hybrid_rag import HybridRAG
from app.components.rag.naive_rag import NaiveRAG

_rag_instance: BaseRAG | None = None


def get_rag() -> BaseRAG:
    """Construct the singleton RAG instance on first call and cache it.
    Call once at FastAPI startup (see main.py's lifespan) so it's built
    eagerly; every later call (from any module) returns the same instance.

    HybridRAG (dense + BM25 via RRF) is the default -- catches exact-name
    keyword matches (menu items, policy terms) that pure embedding
    similarity sometimes under-ranks. NaiveRAG stays available/importable
    for comparison.
    """
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = HybridRAG()
    return _rag_instance


__all__ = [
    "BaseRAG",
    "Document",
    "RAGResponse",
    "NaiveRAG",
    "HybridRAG",
    "get_rag",
]
