import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import ContentSource, Document, DocumentChunk, DocumentStatus
from app.repos.tenant_scope import tenant_scope


async def create_document(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    title: str,
    content_source: ContentSource,
    tags: list[str] | None = None,
    draft_content: str = "",
    source_ref: str | None = None,
) -> Document:
    document = Document(
        tenant_id=tenant_id,
        title=title,
        content_source=content_source,
        tags=tags,
        draft_content=draft_content,
        source_ref=source_ref,
    )
    session.add(document)
    await session.flush()
    return document


async def get_document(session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    stmt = select(Document).where(Document.id == document_id, tenant_scope(Document.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_documents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: DocumentStatus | None = None,
    tag: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Document], int]:
    stmt = select(Document).where(tenant_scope(Document.tenant_id, tenant_id))
    count_stmt = select(func.count()).select_from(Document).where(tenant_scope(Document.tenant_id, tenant_id))
    if status is not None:
        stmt = stmt.where(Document.status == status)
        count_stmt = count_stmt.where(Document.status == status)
    if tag:
        stmt = stmt.where(Document.tags.any(tag))
        count_stmt = count_stmt.where(Document.tags.any(tag))

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Document.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await session.execute(stmt)).scalars().all()
    return list(items), total


async def update_document_draft(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID, **fields: object
) -> Document | None:
    """Edit title/tags/draft_content. Any edit returns the document to
    `draft` status (a previously active/failed/inactive document must be
    re-published to pick up the change) -- see plan's PATCH semantics."""
    document = await get_document(session, tenant_id, document_id)
    if document is None:
        return None

    changed = False
    for key, value in fields.items():
        if value is not None:
            setattr(document, key, value)
            changed = True

    if changed and document.status != DocumentStatus.DRAFT:
        document.status = DocumentStatus.DRAFT

    await session.flush()
    # updated_at is a server-side onupdate default -- refresh so the ORM
    # object reflects the new value instead of lazily reloading it later
    # outside an async-aware context (which raises MissingGreenlet).
    await session.refresh(document)
    return document


async def set_document_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    status: DocumentStatus,
    *,
    last_published_at: datetime | None = None,
) -> Document | None:
    document = await get_document(session, tenant_id, document_id)
    if document is None:
        return None
    document.status = status
    if last_published_at is not None:
        document.last_published_at = last_published_at
    await session.flush()
    await session.refresh(document)
    return document


async def delete_document(session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID) -> bool:
    document = await get_document(session, tenant_id, document_id)
    if document is None:
        return False
    await session.delete(document)  # cascades to document_chunks via FK ondelete
    await session.flush()
    return True


async def insert_chunks(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    chunks: list[dict],
) -> list[DocumentChunk]:
    """Insert new chunk rows, always is_active=False -- see "safe publish"
    pattern in the Phase 2 plan. Caller flips them active only after every
    chunk embeds successfully."""
    rows = [
        DocumentChunk(
            tenant_id=tenant_id,
            document_id=document_id,
            chunk_index=chunk["chunk_index"],
            content=chunk["content"],
            embedding=chunk["embedding"],
            token_count=chunk["token_count"],
            is_active=False,
        )
        for chunk in chunks
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def activate_chunks_and_retire_old(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    new_chunk_ids: list[uuid.UUID],
) -> None:
    """The atomic swap half of safe publish: delete every previous chunk for
    this document not in `new_chunk_ids`, then flip the new ones active.
    Must be called (and committed) only after every chunk in `new_chunk_ids`
    has already been inserted with a valid embedding."""
    await session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            tenant_scope(DocumentChunk.tenant_id, tenant_id),
            DocumentChunk.id.notin_(new_chunk_ids),
        )
    )
    await session.execute(
        update(DocumentChunk).where(DocumentChunk.id.in_(new_chunk_ids)).values(is_active=True)
    )
    await session.flush()


async def discard_chunks(session: AsyncSession, chunk_ids: list[uuid.UUID]) -> None:
    """Roll back a failed publish's partial chunk rows without touching the
    previously-active set."""
    if not chunk_ids:
        return
    await session.execute(delete(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids)))
    await session.flush()


async def search_similar_chunks(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    k: int = 5,
) -> list[DocumentChunk]:
    """Cosine-similarity search over active chunks of active documents --
    used by the bot's RAG retrieval (Phase 4)."""
    stmt = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            tenant_scope(DocumentChunk.tenant_id, tenant_id),
            DocumentChunk.is_active.is_(True),
            Document.status == DocumentStatus.ACTIVE,
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(k)
    )
    return list((await session.execute(stmt)).scalars().all())


async def search_similar_chunks_with_scores(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    k: int = 5,
) -> list[tuple[DocumentChunk, float]]:
    """Same as search_similar_chunks, but also returns each chunk's cosine
    distance (0 = identical, 2 = opposite) -- used by the bot's
    search_documents tool to apply a relevance threshold instead of always
    returning its top-k regardless of how weak the match is."""
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(DocumentChunk, distance.label("distance"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            tenant_scope(DocumentChunk.tenant_id, tenant_id),
            DocumentChunk.is_active.is_(True),
            Document.status == DocumentStatus.ACTIVE,
        )
        .order_by(distance)
        .limit(k)
    )
    return [(chunk, dist) for chunk, dist in (await session.execute(stmt)).all()]


async def list_active_chunks(session: AsyncSession, tenant_id: uuid.UUID, limit: int = 500) -> list[DocumentChunk]:
    """All active chunks of active documents for a tenant -- used by hybrid
    retrieval's BM25 side, which needs to score against the whole candidate
    pool rather than a pre-filtered top-k. Capped at `limit` as a sanity
    bound; if a tenant's real corpus grows past this, BM25 should move to a
    persistent index instead of being rebuilt fresh on every query."""
    stmt = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            tenant_scope(DocumentChunk.tenant_id, tenant_id),
            DocumentChunk.is_active.is_(True),
            Document.status == DocumentStatus.ACTIVE,
        )
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
