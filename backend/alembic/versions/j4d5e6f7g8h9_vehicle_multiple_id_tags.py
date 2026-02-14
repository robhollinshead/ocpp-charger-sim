"""vehicle multiple id_tags

Revision ID: j4d5e6f7g8h9
Revises: i3c4d5e6f7g8
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j4d5e6f7g8h9"
down_revision: Union[str, Sequence[str], None] = "h2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create vehicle_id_tag table
    op.create_table(
        "vehicle_id_tag",
        sa.Column("vehicle_id", sa.String(length=36), nullable=False),
        sa.Column("id_tag", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicle.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("vehicle_id", "id_tag"),
        sa.UniqueConstraint("id_tag"),
    )
    # Backfill from vehicle.id_tag
    op.execute(
        sa.text("INSERT INTO vehicle_id_tag (vehicle_id, id_tag) SELECT id, id_tag FROM vehicle")
    )
    # Drop unique constraint on vehicle.id_tag (SQLite names it; PostgreSQL may differ)
    # SQLite: UNIQUE constraint is part of table; we drop column and recreate table or use batch
    with op.batch_alter_table("vehicle", schema=None) as batch_op:
        batch_op.drop_column("id_tag")


def downgrade() -> None:
    # Re-add id_tag column to vehicle (nullable first to populate)
    op.add_column(
        "vehicle",
        sa.Column("id_tag", sa.String(length=255), nullable=True),
    )
    # Copy first id_tag per vehicle back (arbitrary if multiple)
    op.execute(
        sa.text("""
            UPDATE vehicle SET id_tag = (
                SELECT id_tag FROM vehicle_id_tag
                WHERE vehicle_id_tag.vehicle_id = vehicle.id
                LIMIT 1
            )
        """)
    )
    op.alter_column(
        "vehicle",
        "id_tag",
        existing_type=sa.String(255),
        nullable=False,
    )
    op.create_unique_constraint("uq_vehicle_id_tag", "vehicle", ["id_tag"])
    op.drop_table("vehicle_id_tag")
