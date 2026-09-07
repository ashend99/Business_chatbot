"""Safe-publish orchestration for documents (Phase 2).

Publishing must never leave a previously-searchable document suddenly
unsearchable just because a new edit failed to embed:

1. status -> processing (committed immediately, so concurrent reads see it)
2. chunk + embed draft_content, insert the new chunks as is_active=False
   (the "db pusher" step -- delegated to get_rag().ingest(), see
   components/rag/naive_rag.py)
3. on full success: flip the new chunks active, delete the old ones,
   status -> active, last_published_at -> now
4. on any failure: roll back the new chunk rows (old active chunks are
   never touched), status -> failed

Steps 2-3 run inside one transaction, so a failure partway through never
leaves a mix of old and new chunks active at once.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.components.rag import get_rag
from app.models.documents import DocumentStatus
from app.repos import documents as documents_repo

logger = logging.getLogger(__name__)


class PublishError(ValueError):
    """Raised for expected, user-facing publish failures (not-found, no
    content, already processing) -- as opposed to embedding/API failures,
    which are caught and turned into a `failed` status instead."""


async def publish_document(session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID):
    document = await documents_repo.get_document(session, tenant_id, document_id)
    if document is None:
        raise PublishError("document not found")
    if document.status == DocumentStatus.PROCESSING:
        raise PublishError("document is already being published")
    if not document.draft_content or not document.draft_content.strip():
        raise PublishError("document has no content to publish")

    document.status = DocumentStatus.PROCESSING
    await session.commit()

    try:
        new_rows = await get_rag().ingest(
            [document.draft_content], session=session, tenant_id=tenant_id, document_id=document_id
        )
        if not new_rows:
            raise PublishError("no chunks produced from document content")

        await documents_repo.activate_chunks_and_retire_old(
            session, tenant_id=tenant_id, document_id=document_id, new_chunk_ids=[row.id for row in new_rows]
        )
        document = await documents_repo.set_document_status(
            session, tenant_id, document_id, DocumentStatus.ACTIVE, last_published_at=datetime.now(timezone.utc)
        )
        await session.commit()
        return document
    except Exception:
        await session.rollback()
        logger.exception("publish failed for document %s", document_id)
        await documents_repo.set_document_status(session, tenant_id, document_id, DocumentStatus.FAILED)
        await session.commit()
        raise


async def retry_publish(session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID):
    document = await documents_repo.get_document(session, tenant_id, document_id)
    if document is None:
        raise PublishError("document not found")
    if document.status != DocumentStatus.FAILED:
        raise PublishError("only a failed document can be retried")

    return await publish_document(session, tenant_id, document_id)
