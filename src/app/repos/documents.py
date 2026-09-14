import uuid
from datetime import datetime

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

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
    active_from: datetime | None = None,
    active_until: datetime | None = None,
) -> Document:
    document = Document(
        tenant_id=tenant_id,
        title=title,
        content_source=content_source,
        tags=tags,
        draft_content=draft_content,
        source_ref=source_ref,
        active_from=active_from,
        active_until=active_until,
    )
    session.add(document)
    await session.flush()
    return document


async def get_document(session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document | None:
    stmt = select(Document).where(Document.id == document_id, tenant_scope(Document.tenant_id, tenant_id))
    return (await session.execute(stmt)).scalar_one_or_none()


async def sweep_expired_documents(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Lazy cleanup for temporary documents: any ACTIVE document whose
    active_until has passed gets flipped to INACTIVE (and its chunks
    deactivated to match), so the dashboard's displayed status reflects
    reality without needing a scheduler. This is cosmetic/hygiene, not
    correctness-critical -- the RAG search functions below already exclude
    an expired document's chunks via _within_active_window() regardless of
    whether this sweep has run yet. Called opportunistically from
    list_documents/get_document; the caller must commit."""
    now = func.now()
    expired_ids = (
        await session.execute(
            select(Document.id).where(
                tenant_scope(Document.tenant_id, tenant_id),
                Document.status == DocumentStatus.ACTIVE,
                Document.active_until.is_not(None),
                Document.active_until < now,
            )
        )
    ).scalars().all()
    if not expired_ids:
        return
    await session.execute(update(Document).where(Document.id.in_(expired_ids)).values(status=DocumentStatus.INACTIVE))
    await session.execute(
        update(DocumentChunk).where(DocumentChunk.document_id.in_(expired_ids)).values(is_active=False)
    )
    await session.flush()


async def list_documents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: DocumentStatus | None = None,
    tag: str | None = None,
    expired_only: bool = False,
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
    if expired_only:
        # Not a `status` value -- is_expired is a date comparison, independent
        # of whether the lazy sweep has already flipped this document to
        # inactive yet (see sweep_expired_documents).
        expired_condition = Document.active_until.is_not(None) & (Document.active_until < func.now())
        stmt = stmt.where(expired_condition)
        count_stmt = count_stmt.where(expired_condition)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(Document.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = (await session.execute(stmt)).scalars().all()
    return list(items), total


_CONTENT_FIELDS = {"title", "tags", "draft_content"}
# Fields where an explicit `null` is meaningful (clear it) rather than
# "leave unset" -- unlike title/tags/draft_content, which this function
# always treats a None as "not sent" (see the loop below).
_NULLABLE_FIELDS = {"active_from", "active_until"}


async def update_document_draft(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID, **fields: object
) -> Document | None:
    """Edit title/tags/draft_content, or the active_from/active_until
    window. Editing title/tags/draft_content returns the document to
    `draft` status (a previously active/failed/inactive document must be
    re-published to pick up the change) -- see plan's PATCH semantics.
    Editing only the active window does NOT force a re-publish: the content
    hasn't changed, and RAG search already re-checks the window on every
    query regardless of `status` -- forcing a full re-embed just to move a
    date would be wasteful (this is exactly the "reuse next season" case)."""
    document = await get_document(session, tenant_id, document_id)
    if document is None:
        return None

    content_changed = False
    for key, value in fields.items():
        if value is not None or key in _NULLABLE_FIELDS:
            setattr(document, key, value)
            if key in _CONTENT_FIELDS:
                content_changed = True

    if content_changed and document.status != DocumentStatus.DRAFT:
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


def _within_active_window() -> ColumnElement[bool]:
    """True when `now` falls inside the document's optional active_from /
    active_until window -- both null (the common, non-temporary case) always
    passes. Applied to every RAG search below so a temporary document (e.g.
    a seasonal offer) is instantly excluded/included at its boundaries,
    with no scheduled job needed for correctness."""
    now = func.now()
    return and_(
        or_(Document.active_from.is_(None), Document.active_from <= now),
        or_(Document.active_until.is_(None), Document.active_until >= now),
    )


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
            _within_active_window(),
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
            _within_active_window(),
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
            _within_active_window(),
        )
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
