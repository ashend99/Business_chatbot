"""OpenAI embeddings client for the documents publish pipeline (Phase 2)."""

import asyncio
import logging

from openai import AsyncOpenAI, RateLimitError

from app.core.config import settings
from common import PROJECT_CONFIG

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.openai_api_key)

_embedding_config = PROJECT_CONFIG.get("documents", {}).get("embedding", {})
EMBEDDING_MODEL = _embedding_config.get("model", "text-embedding-3-small")
BATCH_SIZE = _embedding_config.get("batch_size", 100)
MAX_RETRIES = _embedding_config.get("max_retries", 5)
INITIAL_BACKOFF_SECONDS = _embedding_config.get("initial_backoff_seconds", 1.0)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of chunk strings, batching requests to keep request
    overhead down. Raises on failure -- callers (publishing.py) rely on this
    to abort the publish before any chunk rows are written."""
    if not texts:
        return []

    embeddings: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        embeddings.extend(await _embed_batch(batch))
    return embeddings


async def _embed_batch(batch: list[str]) -> list[list[float]]:
    delay = INITIAL_BACKOFF_SECONDS
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = await _client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
            return [item.embedding for item in response.data]
        except RateLimitError:
            if attempt == MAX_RETRIES:
                raise
            logger.warning("embeddings rate-limited, retrying in %.1fs (attempt %d/%d)", delay, attempt, MAX_RETRIES)
            await asyncio.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")  # pragma: no cover
