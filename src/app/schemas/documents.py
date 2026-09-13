import uuid
from datetime import datetime

from pydantic import BaseModel, HttpUrl, model_validator

from app.models.documents import ContentSource, DocumentStatus


class DocumentCreate(BaseModel):
    """Create a document via pasted text, or via placeholder metadata ahead
    of a file upload (POST /tenant/documents/{id}/upload). URL imports are
    created in one shot by DocumentImportUrlRequest instead."""

    title: str
    content_source: ContentSource = ContentSource.PASTE
    tags: list[str] | None = None
    draft_content: str | None = None
    # Optional "temporary document" window (e.g. a seasonal offer) -- see
    # models/documents.py's Document.active_from/active_until.
    active_from: datetime | None = None
    active_until: datetime | None = None

    # a model-level (not field-level) validator: field_validator would be
    # skipped here because draft_content is often left at its None default,
    # and pydantic doesn't run per-field validators over defaulted values.
    @model_validator(mode="after")
    def _check_source_rules(self) -> "DocumentCreate":
        if self.content_source == ContentSource.URL:
            raise ValueError("use POST /tenant/documents/import-url for url imports")
        has_content = self.draft_content and self.draft_content.strip()
        if self.content_source == ContentSource.PASTE and not has_content:
            raise ValueError("draft_content is required when content_source is 'paste'")
        return self


class DocumentImportUrlRequest(BaseModel):
    title: str
    url: HttpUrl
    tags: list[str] | None = None
    active_from: datetime | None = None
    active_until: datetime | None = None


class DocumentUpdate(BaseModel):
    # title/tags/draft_content: like the rest of this codebase's PATCH
    # endpoints, leaving one unset keeps it, and an explicit `null` is
    # currently ignored too (repos/documents.py's update_document_draft
    # skips None for these). active_from/active_until are the exception --
    # an explicit `null` there does clear the bound, since "remove the
    # expiry" is a normal action for a temporary document.
    title: str | None = None
    tags: list[str] | None = None
    draft_content: str | None = None
    active_from: datetime | None = None
    active_until: datetime | None = None


class DocumentRead(BaseModel):
    id: uuid.UUID
    title: str
    content_source: ContentSource
    source_ref: str | None
    draft_content: str
    tags: list[str] | None
    status: DocumentStatus
    last_published_at: datetime | None
    active_from: datetime | None
    active_until: datetime | None
    is_expired: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    id: uuid.UUID
    title: str
    content_source: ContentSource
    tags: list[str] | None
    status: DocumentStatus
    last_published_at: datetime | None
    active_from: datetime | None
    active_until: datetime | None
    is_expired: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int
    page: int
    page_size: int
