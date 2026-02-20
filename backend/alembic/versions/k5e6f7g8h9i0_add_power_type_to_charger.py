"""add power_type to charger

Revision ID: k5e6f7g8h9i0
Revises: j4d5e6f7g8h9
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k5e6f7g8h9i0"
down_revision: Union[str, Sequence[str], None] = "j4d5e6f7g8h9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add power_type column to charger table with default 'DC' for backward compatibility."""
    op.add_column(
        "charger",
        sa.Column("power_type", sa.String(length=4), nullable=False, server_default="DC"),
    )


def downgrade() -> None:
    """Remove power_type column from charger table."""
    op.drop_column("charger", "power_type")
