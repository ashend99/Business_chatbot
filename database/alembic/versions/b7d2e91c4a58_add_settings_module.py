"""add settings module

Revision ID: b7d2e91c4a58
Revises: f3a9c7b1d2e4
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7d2e91c4a58'
down_revision: Union[str, Sequence[str], None] = 'f3a9c7b1d2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # DB stores the Python Enum member *name* (SQLAlchemy default) -- see
    # 91ef6a57c6e0 for the same one-way ADD VALUE pattern
    op.execute("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'PENDING_CONFIRMATION'")
    op.add_column("orders", sa.Column("currency_code", sa.String(length=3), nullable=True))

    bot_tone = sa.Enum("FORMAL", "FRIENDLY", "CASUAL", name="bot_tone")
    negotiation_mode = sa.Enum("FIXED", "ESCALATE", name="negotiation_mode")
    order_confirmation_mode = sa.Enum("BOT", "HUMAN", name="order_confirmation_mode")

    op.create_table(
        "tenant_admin_settings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("ordering_allowed", sa.Boolean(), nullable=False),
        sa.Column("catalog_allowed", sa.Boolean(), nullable=False),
        sa.Column("documents_allowed", sa.Boolean(), nullable=False),
        sa.Column("leads_allowed", sa.Boolean(), nullable=False),
        sa.Column("allowed_channels", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("llm_model", sa.String(length=100), nullable=True),
        sa.Column("monthly_message_limit", sa.Integer(), nullable=True),
        sa.Column("max_documents", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )
    op.create_table(
        "tenant_settings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("bot_name", sa.String(length=100), nullable=True),
        sa.Column("tone", bot_tone, nullable=False),
        sa.Column("language", sa.String(length=50), nullable=False),
        sa.Column("welcome_message", sa.Text(), nullable=True),
        sa.Column("fallback_message", sa.Text(), nullable=True),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column("bot_enabled", sa.Boolean(), nullable=False),
        sa.Column("ordering_enabled", sa.Boolean(), nullable=False),
        sa.Column("catalog_enabled", sa.Boolean(), nullable=False),
        sa.Column("documents_enabled", sa.Boolean(), nullable=False),
        sa.Column("leads_enabled", sa.Boolean(), nullable=False),
        sa.Column("delivery_enabled", sa.Boolean(), nullable=False),
        sa.Column("pickup_enabled", sa.Boolean(), nullable=False),
        sa.Column("cash_on_delivery", sa.Boolean(), nullable=False),
        sa.Column("min_order_value", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("negotiation_mode", negotiation_mode, nullable=False),
        sa.Column("order_confirmation_mode", order_confirmation_mode, nullable=False),
        sa.Column("notify_emails", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("notify_new_lead", sa.Boolean(), nullable=False),
        sa.Column("notify_new_order", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )

    # Backfill every existing tenant with generic defaults (USD/UTC) so the
    # resolver never meets a tenant with no row; an admin then sets the real
    # currency/timezone per tenant via the superadmin API.
    op.execute(
        """
        INSERT INTO tenant_admin_settings (
            tenant_id, currency_code, ordering_allowed, catalog_allowed,
            documents_allowed, leads_allowed, allowed_channels
        )
        SELECT id, 'USD', true, true, true, true,
               ARRAY['website_widget','facebook','instagram','whatsapp']
        FROM tenants
        """
    )
    op.execute(
        """
        INSERT INTO tenant_settings (
            tenant_id, timezone, tone, language, bot_enabled, ordering_enabled,
            catalog_enabled, documents_enabled, leads_enabled, delivery_enabled,
            pickup_enabled, cash_on_delivery, negotiation_mode,
            order_confirmation_mode, notify_emails, notify_new_lead,
            notify_new_order
        )
        SELECT id, 'UTC', 'FRIENDLY', 'English', true, true, true, true, true,
               true, true, false, 'FIXED', 'BOT', ARRAY[]::varchar[], true, true
        FROM tenants
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("tenant_settings")
    op.drop_table("tenant_admin_settings")
    sa.Enum(name="order_confirmation_mode").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="negotiation_mode").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="bot_tone").drop(op.get_bind(), checkfirst=True)
    op.drop_column("orders", "currency_code")
    # Postgres has no "remove enum value" -- PENDING_CONFIRMATION stays in
    # order_status on downgrade (same accepted tradeoff as the leads enum growth)
