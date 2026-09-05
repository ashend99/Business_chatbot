import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class ConversationChannel(Enum):
    """Which channel a chat came through -- distinct from
    tenants.ChannelTypes, which tracks *connected social accounts*
    (OAuth-linked pages), not per-chat channel. website_widget has no
    connection record at all."""

    WEBSITE_WIDGET = "website_widget"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"


class ConversationStatus(Enum):
    OPEN = "open"
    IDLE = "idle"
    CLOSED = "closed"


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Conversation(TenantScopedMixin, Base):
    """The business-record side of a chat -- who/where/when. The agent's
    own turn-by-turn working memory lives separately in LangGraph's
    checkpoint tables, keyed by this row's id as thread_id."""

    __tablename__ = "conversations"

    channel_type: Mapped[ConversationChannel] = mapped_column(
        SAEnum(ConversationChannel, name="conversation_channel"), nullable=False
    )
    external_user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(ConversationStatus, name="conversation_status"), default=ConversationStatus.OPEN, nullable=False
    )
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Message(TenantScopedMixin, Base):
    """Human-readable transcript -- source of truth for the future Inbox
    dashboard (Phase 10). Not read back into the agent's own context;
    that's the checkpointer's job."""

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole, name="message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
