import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_tenant_id
from app.db.session import get_db_session
from app.models.documents import ContentSource, DocumentStatus
from app.repos import documents as documents_repo
from app.schemas.documents import (
    DocumentCreate,
    DocumentImportUrlRequest,
    DocumentListItem,
    DocumentListResponse,
    DocumentRead,
    DocumentUpdate,
)
from app.services import file_parsing
from app.services.publishing import PublishError, publish_document, retry_publish
from common import PROJECT_CONFIG

router = APIRouter(prefix="/tenant/documents", tags=["documents"])

_PARSERS = {
    "pdf": file_parsing.parse_pdf,
    "docx": file_parsing.parse_docx,
    "txt": file_parsing.parse_txt,
}

_upload_config = PROJECT_CONFIG.get("documents", {}).get("upload", {})
MAX_DOCUMENT_CHARS = _upload_config.get("max_characters", 200_000)
MAX_DOCUMENT_UPLOAD_MB = _upload_config.get("max_size_mb", 10)


def _extension_of(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _enforce_char_limit(text: str) -> str:
    if len(text) > MAX_DOCUMENT_CHARS:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"extracted content exceeds the {MAX_DOCUMENT_CHARS}-character limit",
        )
    return text


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    document = await documents_repo.create_document(
        session,
        tenant_id=tenant_id,
        title=payload.title,
        content_source=payload.content_source,
        tags=payload.tags,
        draft_content=payload.draft_content or "",
        active_from=payload.active_from,
        active_until=payload.active_until,
    )
    await session.commit()
    return DocumentRead.model_validate(document)


@router.post("/import-url", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def import_url(
    payload: DocumentImportUrlRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    try:
        text = await file_parsing.fetch_url_text(str(payload.url))
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"could not fetch url: {exc}") from exc
    text = _enforce_char_limit(text)

    document = await documents_repo.create_document(
        session,
        tenant_id=tenant_id,
        title=payload.title,
        content_source=ContentSource.URL,
        tags=payload.tags,
        draft_content=text,
        source_ref=str(payload.url),
        active_from=payload.active_from,
        active_until=payload.active_until,
    )
    await session.commit()
    return DocumentRead.model_validate(document)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    status_filter: DocumentStatus | None = Query(None, alias="status"),
    tag: str | None = None,
    expired: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentListResponse:
    # Lazy cleanup: flip any now-expired temporary document to inactive
    # before listing, so the returned status is never stale. Cheap no-op
    # when nothing has expired; see sweep_expired_documents's docstring.
    await documents_repo.sweep_expired_documents(session, tenant_id)
    await session.commit()

    items, total = await documents_repo.list_documents(
        session, tenant_id, status=status_filter, tag=tag, expired_only=expired, page=page, page_size=page_size
    )
    return DocumentListResponse(
        items=[DocumentListItem.model_validate(d) for d in items], total=total, page=page, page_size=page_size
    )


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    await documents_repo.sweep_expired_documents(session, tenant_id)
    await session.commit()

    document = await documents_repo.get_document(session, tenant_id, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return DocumentRead.model_validate(document)


@router.post("/{document_id}/upload", response_model=DocumentRead)
async def upload_document(
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    document = await documents_repo.get_document(session, tenant_id, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    if document.content_source != ContentSource.UPLOAD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "document was not created with content_source='upload'")

    extension = _extension_of(file.filename)
    parser = _PARSERS.get(extension)
    if parser is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported file type -- use PDF, DOCX, or TXT")

    data = await file.read()
    max_bytes = MAX_DOCUMENT_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"file exceeds the {MAX_DOCUMENT_UPLOAD_MB}MB limit"
        )

    try:
        text = parser(data)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"could not extract text: {exc}") from exc
    text = _enforce_char_limit(text)

    document = await documents_repo.update_document_draft(
        session, tenant_id, document_id, draft_content=text, source_ref=file.filename
    )
    await session.commit()
    return DocumentRead.model_validate(document)


@router.patch("/{document_id}", response_model=DocumentRead)
async def update_document(
    document_id: uuid.UUID,
    payload: DocumentUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    document = await documents_repo.update_document_draft(
        session, tenant_id, document_id, **payload.model_dump(exclude_unset=True)
    )
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    await session.commit()
    return DocumentRead.model_validate(document)


@router.patch("/{document_id}/deactivate", response_model=DocumentRead)
async def deactivate_document(
    document_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    document = await documents_repo.set_document_status(session, tenant_id, document_id, DocumentStatus.INACTIVE)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    await session.commit()
    return DocumentRead.model_validate(document)


@router.post("/{document_id}/publish", response_model=DocumentRead)
async def publish(
    document_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    try:
        document = await publish_document(session, tenant_id, document_id)
    except PublishError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        # embedding/API failure -- publish_document already recorded status=failed
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "publish failed while embedding content") from exc
    return DocumentRead.model_validate(document)


@router.post("/{document_id}/retry", response_model=DocumentRead)
async def retry(
    document_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    try:
        document = await retry_publish(session, tenant_id, document_id)
    except PublishError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "publish failed while embedding content") from exc
    return DocumentRead.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    deleted = await documents_repo.delete_document(session, tenant_id, document_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    await session.commit()
