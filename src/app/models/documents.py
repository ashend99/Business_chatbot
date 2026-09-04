import uuid
from datetime import datetime
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base, TenantScopedMixin


class ContentSource(Enum):
    UPLOAD = "upload"
    PASTE = "paste"
    URL = "url"


class DocumentStatus(Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    ACTIVE = "active"
    FAILED = "failed"
    INACTIVE = "inactive"


class Document(TenantScopedMixin, Base):
    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content_source: Mapped[ContentSource] = mapped_column(
        SAEnum(ContentSource, name="document_content_source"), nullable=False
    )
    # original filename (upload) or source URL (url import) -- kept for reference only
    source_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # latest edited text, post-extraction, pre-publish
    draft_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status"), default=DocumentStatus.DRAFT, nullable=False
    )
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentChunk(TenantScopedMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # dimension must match settings.embedding_dimensions / the chosen OpenAI embedding model
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimensions), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # "safe publish" pattern: new chunks are inserted inactive and only flipped
    # to active once the whole publish succeeds -- see services/publishing.py
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
