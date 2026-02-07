"""create_charger_table

Revision ID: ea5f507c967c
Revises: a4ef9ad83d82
Create Date: 2026-02-07 13:56:21.347069

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea5f507c967c'
down_revision: Union[str, Sequence[str], None] = 'a4ef9ad83d82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "charger",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=False),
        sa.Column("charge_point_id", sa.String(length=255), nullable=False),
        sa.Column("connection_url", sa.String(length=512), nullable=False),
        sa.Column("charger_name", sa.String(length=255), nullable=False),
        sa.Column("ocpp_version", sa.String(length=32), nullable=False, server_default="1.6"),
        sa.ForeignKeyConstraint(["location_id"], ["location.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("charge_point_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("charger", if_exists=True)
