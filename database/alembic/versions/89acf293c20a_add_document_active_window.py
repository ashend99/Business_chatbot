"""add document active window

Revision ID: 89acf293c20a
Revises: ad26bea05baf
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '89acf293c20a'
down_revision: Union[str, Sequence[str], None] = 'ad26bea05baf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("documents", sa.Column("active_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("active_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("documents", "active_until")
    op.drop_column("documents", "active_from")
