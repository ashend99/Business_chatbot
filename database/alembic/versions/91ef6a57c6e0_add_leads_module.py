"""add leads module

Revision ID: 91ef6a57c6e0
Revises: 02f028f85c21
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '91ef6a57c6e0'
down_revision: Union[str, Sequence[str], None] = '02f028f85c21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # the bot only ever writes INTERESTED/NEW (see models/leads.py); these
    # three are dashboard-only manual transitions. Adding enum values is
    # one-way in Postgres -- see downgrade()'s note.
    # DB stores the Python Enum *member name* (SQLAlchemy's Enum default),
    # not its .value -- matches the existing "NEW"/"INTERESTED" values from
    # the original migration, not the lowercase LeadStatus.value strings
    op.execute("ALTER TYPE lead_status ADD VALUE IF NOT EXISTS 'CONTACTED'")
    op.execute("ALTER TYPE lead_status ADD VALUE IF NOT EXISTS 'CONVERTED'")
    op.execute("ALTER TYPE lead_status ADD VALUE IF NOT EXISTS 'LOST'")

    op.add_column("leads", sa.Column("deal_value", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("leads", sa.Column("notes", sa.Text(), nullable=True))

    lead_field_type = sa.Enum("TEXT", "PHONE", "EMAIL", "DATE", "TEXTAREA", name="lead_field_type")
    op.create_table(
        "lead_field_defs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("field_key", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("field_type", lead_field_type, nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lead_field_defs_tenant_id"), "lead_field_defs", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_lead_field_defs_tenant_id"), table_name="lead_field_defs")
    op.drop_table("lead_field_defs")
    sa.Enum(name="lead_field_type").drop(op.get_bind(), checkfirst=True)

    op.drop_column("leads", "notes")
    op.drop_column("leads", "deal_value")

    # Postgres has no "remove enum value" -- leaving contacted/converted/lost
    # in the type on downgrade is the accepted tradeoff (matches how the
    # rest of this migration chain treats one-way enum growth)
