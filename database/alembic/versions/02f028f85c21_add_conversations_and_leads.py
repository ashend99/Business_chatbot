"""add conversations, messages, and leads

Revision ID: 02f028f85c21
Revises: 4155a7697a76
Create Date: 2026-09-05 00:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '02f028f85c21'
down_revision: Union[str, Sequence[str], None] = '4155a7697a76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conversation_channel = sa.Enum("WEBSITE_WIDGET", "FACEBOOK", "INSTAGRAM", "WHATSAPP", name="conversation_channel")
    conversation_status = sa.Enum("OPEN", "IDLE", "CLOSED", name="conversation_status")
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("channel_type", conversation_channel, nullable=False),
        sa.Column("external_user_id", sa.Text(), nullable=False),
        sa.Column("status", conversation_status, nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversations_tenant_id"), "conversations", ["tenant_id"])
    op.create_index(op.f("ix_conversations_external_user_id"), "conversations", ["external_user_id"])

    message_role = sa.Enum("USER", "ASSISTANT", "SYSTEM", name="message_role")
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_tenant_id"), "messages", ["tenant_id"])
    op.create_index(op.f("ix_messages_conversation_id"), "messages", ["conversation_id"])

    lead_status = sa.Enum("NEW", "INTERESTED", name="lead_status")
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("matched_variant_id", sa.Uuid(), nullable=True),
        sa.Column("status", lead_status, nullable=False),
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_channel", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_variant_id"], ["variants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_leads_tenant_id"), "leads", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("leads")
    sa.Enum(name="lead_status").drop(op.get_bind(), checkfirst=True)
    op.drop_table("messages")
    sa.Enum(name="message_role").drop(op.get_bind(), checkfirst=True)
    op.drop_table("conversations")
    sa.Enum(name="conversation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="conversation_channel").drop(op.get_bind(), checkfirst=True)
