import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Tenant(TimestampMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(nullable=True)

class InviteTokens(TimestampMixin, Base):
    __tablename__ = "invite_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # invites/reset links must not be valid forever
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class ChannelTypes(Enum):
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"

class ChannelStatuses(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class ChannelConnections(TimestampMixin, Base):
    __tablename__ = "channel_connections"
    # one connection per external account platform-wide, and required for the
    # tenant-resolution lookup on inbound webhooks
    __table_args__ = (UniqueConstraint("channel_type", "external_account_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    channel_type: Mapped[ChannelTypes] = mapped_column(SAEnum(ChannelTypes, name="channel_types"), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted_access_token: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[ChannelStatuses] = mapped_column(
        SAEnum(ChannelStatuses, name="channel_statuses"), default=ChannelStatuses.ACTIVE, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class ApiKeyTypes(Enum):
    WIDGET_SITE_KEY = "widget_site_key"
    API_SECRET = "api_secret"

class TenantApiKeys(TimestampMixin, Base):
    __tablename__ = "tenant_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    # short, non-secret identifier shown in the dashboard -- the real secret is never stored/shown again
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    hashed_secret: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    key_type: Mapped[ApiKeyTypes] = mapped_column(SAEnum(ApiKeyTypes, name="api_key_types"), nullable=False)
    allowed_domains: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)