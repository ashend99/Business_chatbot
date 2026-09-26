"""Documents: draft/publish lifecycle, the "safe publish" swap, the optional
active window, and hybrid retrieval over the result (with fake embeddings)."""

from datetime import UTC, datetime, timedelta

import pytest
from factories import make_tenant
from sqlalchemy import select

from app.components.rag import get_rag, hybrid_rag
from app.models.documents import ContentSource, DocumentChunk, DocumentStatus
from app.repos import documents as documents_repo
from app.services.publishing import PublishError, publish_document, retry_publish

NOW = datetime.now(UTC)
REFUND = "Refunds are accepted within seven days of purchase with a receipt."
HOURS = "We are open from nine in the morning until six in the evening."


@pytest.fixture
async def tenant(session):
    return await make_tenant(session)


async def new_doc(session, tenant, content: str = REFUND, **kwargs):
    doc = await documents_repo.create_document(
        session,
        tenant_id=tenant.id,
        title=kwargs.pop("title", "Policy"),
        content_source=ContentSource.PASTE,
        draft_content=content,
        **kwargs,
    )
    await session.commit()
    return doc


async def chunks_of(session, document_id) -> list[DocumentChunk]:
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list((await session.execute(stmt)).scalars().all())


# ---- publish ----------------------------------------------------------------


async def test_publish_activates_chunks(session, tenant) -> None:
    doc = await new_doc(session, tenant)
    published = await publish_document(session, tenant.id, doc.id)
    assert published.status == DocumentStatus.ACTIVE
    assert published.last_published_at is not None
    chunks = await chunks_of(session, doc.id)
    assert [c.content for c in chunks] == [REFUND]
    assert all(c.is_active for c in chunks)
    assert chunks[0].token_count == len(REFUND) // 4


async def test_republish_replaces_the_old_chunks(session, tenant) -> None:
    doc = await new_doc(session, tenant)
    await publish_document(session, tenant.id, doc.id)
    await documents_repo.update_document_draft(session, tenant.id, doc.id, draft_content=HOURS)
    await session.commit()
    await publish_document(session, tenant.id, doc.id)
    assert [c.content for c in await chunks_of(session, doc.id)] == [HOURS]


async def test_failed_publish_keeps_the_previous_version_searchable(
    session, tenant, monkeypatch
) -> None:
    doc = await new_doc(session, tenant)
    await publish_document(session, tenant.id, doc.id)
    await documents_repo.update_document_draft(session, tenant.id, doc.id, draft_content=HOURS)
    await session.commit()

    async def broken_embed(texts):
        raise RuntimeError("embedding API down")

    monkeypatch.setattr(hybrid_rag, "embed_texts", broken_embed)
    with pytest.raises(RuntimeError):
        await publish_document(session, tenant.id, doc.id)

    assert (
        await documents_repo.get_document(session, tenant.id, doc.id)
    ).status == DocumentStatus.FAILED
    chunks = await chunks_of(session, doc.id)
    assert [(c.content, c.is_active) for c in chunks] == [(REFUND, True)]


async def test_retry_only_for_failed_documents(session, tenant, monkeypatch) -> None:
    doc = await new_doc(session, tenant)
    with pytest.raises(PublishError, match="only a failed document"):
        await retry_publish(session, tenant.id, doc.id)

    async def broken_embed(texts):
        raise RuntimeError("down")

    monkeypatch.setattr(hybrid_rag, "embed_texts", broken_embed)
    with pytest.raises(RuntimeError):
        await publish_document(session, tenant.id, doc.id)
    monkeypatch.undo()

    retried = await retry_publish(session, tenant.id, doc.id)
    assert retried.status == DocumentStatus.ACTIVE


async def test_publish_preconditions(session, tenant) -> None:
    import uuid

    with pytest.raises(PublishError, match="not found"):
        await publish_document(session, tenant.id, uuid.uuid4())

    empty = await documents_repo.create_document(
        session,
        tenant_id=tenant.id,
        title="Empty",
        content_source=ContentSource.UPLOAD,
        draft_content="  ",
    )
    await session.commit()
    with pytest.raises(PublishError, match="no content"):
        await publish_document(session, tenant.id, empty.id)

    busy = await new_doc(session, tenant)
    await documents_repo.set_document_status(session, tenant.id, busy.id, DocumentStatus.PROCESSING)
    await session.commit()
    with pytest.raises(PublishError, match="already being published"):
        await publish_document(session, tenant.id, busy.id)


# ---- drafts -----------------------------------------------------------------


async def test_content_edit_returns_document_to_draft(session, tenant) -> None:
    doc = await new_doc(session, tenant)
    await publish_document(session, tenant.id, doc.id)
    edited = await documents_repo.update_document_draft(
        session, tenant.id, doc.id, title="New title", tags=None
    )
    assert edited.status == DocumentStatus.DRAFT
    assert edited.title == "New title"


async def test_window_only_edit_keeps_status_and_null_clears_it(session, tenant) -> None:
    doc = await new_doc(session, tenant, active_until=NOW + timedelta(days=1))
    await publish_document(session, tenant.id, doc.id)
    edited = await documents_repo.update_document_draft(
        session, tenant.id, doc.id, active_until=None, title=None
    )
    assert edited.status == DocumentStatus.ACTIVE
    assert edited.active_until is None
    assert edited.title == "Policy"  # None for content fields means "not sent"


# ---- active window ----------------------------------------------------------


@pytest.mark.parametrize(
    ("window", "visible"),
    [
        ({}, True),
        ({"active_from": NOW - timedelta(days=1), "active_until": NOW + timedelta(days=1)}, True),
        ({"active_from": NOW + timedelta(days=1)}, False),
        ({"active_until": NOW - timedelta(minutes=1)}, False),
    ],
)
async def test_rag_search_respects_the_active_window(
    session, tenant, window: dict, visible: bool
) -> None:
    doc = await new_doc(session, tenant, **window)
    await publish_document(session, tenant.id, doc.id)
    found = await documents_repo.list_active_chunks(session, tenant.id)
    assert bool(found) is visible
    docs = await get_rag().retrieve("refund policy", session=session, tenant_id=tenant.id)
    assert bool(docs) is visible


async def test_sweep_deactivates_expired_documents(session, tenant) -> None:
    expired = await new_doc(
        session, tenant, title="Old promo", active_until=NOW + timedelta(days=1)
    )
    current = await new_doc(session, tenant, content=HOURS, title="Hours")
    await publish_document(session, tenant.id, expired.id)
    await publish_document(session, tenant.id, current.id)
    await documents_repo.update_document_draft(
        session, tenant.id, expired.id, active_until=NOW - timedelta(seconds=1)
    )
    await session.commit()

    await documents_repo.sweep_expired_documents(session, tenant.id)
    await session.commit()

    assert (
        await documents_repo.get_document(session, tenant.id, expired.id)
    ).status == DocumentStatus.INACTIVE
    assert not any(c.is_active for c in await chunks_of(session, expired.id))
    assert (
        await documents_repo.get_document(session, tenant.id, current.id)
    ).status == DocumentStatus.ACTIVE


async def test_inactive_document_is_not_searched(session, tenant) -> None:
    doc = await new_doc(session, tenant)
    await publish_document(session, tenant.id, doc.id)
    await documents_repo.set_document_status(session, tenant.id, doc.id, DocumentStatus.INACTIVE)
    await session.commit()
    assert await documents_repo.list_active_chunks(session, tenant.id) == []


# ---- listing ----------------------------------------------------------------


async def test_list_documents_filters_and_paginates(session, tenant) -> None:
    for i in range(3):
        await new_doc(session, tenant, title=f"Doc {i}", tags=["faq"] if i else ["menu"])
    await new_doc(session, tenant, title="Expired", active_until=NOW - timedelta(days=1))

    _, total = await documents_repo.list_documents(session, tenant.id)
    assert total == 4
    page, total = await documents_repo.list_documents(session, tenant.id, page=2, page_size=3)
    assert (len(page), total) == (1, 4)
    assert (await documents_repo.list_documents(session, tenant.id, tag="faq"))[1] == 2
    assert [
        d.title
        for d in (await documents_repo.list_documents(session, tenant.id, expired_only=True))[0]
    ] == ["Expired"]
    assert (await documents_repo.list_documents(session, tenant.id, status=DocumentStatus.ACTIVE))[
        1
    ] == 0


# ---- retrieval --------------------------------------------------------------


async def test_hybrid_retrieve_ranks_the_relevant_chunk_first(session, tenant) -> None:
    for title, content in [
        ("Refunds", REFUND),
        ("Hours", HOURS),
        ("Parking", "Free parking is behind the building."),
    ]:
        await publish_document(
            session, tenant.id, (await new_doc(session, tenant, content, title=title)).id
        )

    docs = await get_rag().retrieve(
        "are refunds accepted with a receipt", session=session, tenant_id=tenant.id, top_k=2
    )
    assert docs[0].content == REFUND
    assert len(docs) == 2
    assert docs[0].metadata["dense_distance"] < 0.75
