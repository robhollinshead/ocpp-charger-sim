"""create_vehicle_table

Revision ID: i3c4d5e6f7g8
Revises: h2b3c4d5e6f7
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i3c4d5e6f7g8"
down_revision: Union[str, Sequence[str], None] = "h2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create vehicle table."""
    op.create_table(
        "vehicle",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("id_tag", sa.String(length=255), nullable=False),
        sa.Column("battery_capacity_kwh", sa.Numeric(10, 2), nullable=False),
        sa.Column("location_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["location.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("id_tag"),
    )


def downgrade() -> None:
    """Drop vehicle table."""
    op.drop_table("vehicle", if_exists=True)
