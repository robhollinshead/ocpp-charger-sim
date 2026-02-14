"""security_profile_and_basic_auth

Revision ID: h2c3d4e5f6g7
Revises: i3c4d5e6f7g8
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h2c3d4e5f6g7"
down_revision: Union[str, Sequence[str], None] = "i3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add security_profile and basic_auth_password to charger."""
    op.add_column(
        "charger",
        sa.Column("security_profile", sa.String(length=32), nullable=False, server_default="none"),
    )
    op.add_column(
        "charger",
        sa.Column("basic_auth_password", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Remove security_profile and basic_auth_password from charger."""
    op.drop_column("charger", "basic_auth_password")
    op.drop_column("charger", "security_profile")
