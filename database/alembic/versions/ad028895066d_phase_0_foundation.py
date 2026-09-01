"""phase 0 foundation

Revision ID: ad028895066d
Revises: 
Create Date: 2026-09-01 23:38:28.280185

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad028895066d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("contact_person", sa.String(length=255), nullable=True),
        sa.Column("contact_number", sa.String(length=50), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenants_slug"), "tenants", ["slug"], unique=True)
    op.create_index(op.f("ix_tenants_email"), "tenants", ["email"], unique=True)

    op.create_table(
        "invite_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_invite_tokens_token_hash"), "invite_tokens", ["token_hash"], unique=True)

    op.create_table(
        "tenant_admins",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_index(op.f("ix_tenant_admins_username"), "tenant_admins", ["username"], unique=True)

    channel_types = sa.Enum("FACEBOOK", "TWITTER", "INSTAGRAM", name="channel_types")
    channel_statuses = sa.Enum("ACTIVE", "INACTIVE", name="channel_statuses")
    op.create_table(
        "channel_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("channel_type", channel_types, nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("account_name", sa.String(length=255), nullable=True),
        sa.Column("encrypted_access_token", sa.String(), nullable=False),
        sa.Column("status", channel_statuses, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_type", "external_account_id"),
    )
    op.create_index(
        op.f("ix_channel_connections_external_account_id"),
        "channel_connections",
        ["external_account_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("channel_connections")
    sa.Enum(name="channel_statuses").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="channel_types").drop(op.get_bind(), checkfirst=True)
    op.drop_table("tenant_admins")
    op.drop_table("invite_tokens")
    op.drop_table("tenants")
