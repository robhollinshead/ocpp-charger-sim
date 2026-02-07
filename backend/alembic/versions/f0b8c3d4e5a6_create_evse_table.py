"""create_evse_table

Revision ID: f0b8c3d4e5a6
Revises: ea5f507c967c
Create Date: 2026-02-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f0b8c3d4e5a6"
down_revision: Union[str, Sequence[str], None] = "ea5f507c967c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "evse",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("charger_id", sa.String(length=36), nullable=False),
        sa.Column("evse_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["charger_id"], ["charger.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("charger_id", "evse_id", name="uq_evse_charger_id_evse_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("evse", if_exists=True)
