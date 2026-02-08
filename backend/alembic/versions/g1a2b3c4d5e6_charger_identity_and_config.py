"""charger_identity_and_config

Revision ID: g1a2b3c4d5e6
Revises: f0b8c3d4e5a6
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "g1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "f0b8c3d4e5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Default config for existing chargers (OCPP config keys).
DEFAULT_CONFIG_JSON = (
    '{"HeartbeatInterval": 120, "ConnectionTimeOut": 60, "MeterValuesSampleInterval": 30, '
    '"ClockAlignedDataInterval": 900, "AuthorizeRemoteTxRequests": true, "LocalAuthListEnabled": true}'
)


def upgrade() -> None:
    """Add charge_point_vendor, charge_point_model, firmware_version and config to charger."""
    op.add_column(
        "charger",
        sa.Column("charge_point_vendor", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "charger",
        sa.Column("charge_point_model", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "charger",
        sa.Column("firmware_version", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "charger",
        sa.Column("config", sa.JSON(), nullable=True),
    )

    # Backfill existing rows with defaults.
    op.execute(
        sa.text(
            "UPDATE charger SET charge_point_vendor = 'FastCharge', "
            "charge_point_model = 'Pro 150', firmware_version = '2.4.1' "
            "WHERE charge_point_vendor IS NULL"
        )
    )
    # Backfill config (SQLite stores JSON as text; escape single quotes).
    op.execute(
        "UPDATE charger SET config = '"
        + DEFAULT_CONFIG_JSON.replace("'", "''")
        + "' WHERE config IS NULL"
    )


def downgrade() -> None:
    """Remove identity and config columns from charger."""
    op.drop_column("charger", "config")
    op.drop_column("charger", "firmware_version")
    op.drop_column("charger", "charge_point_model")
    op.drop_column("charger", "charge_point_vendor")
