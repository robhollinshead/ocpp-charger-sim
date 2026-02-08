"""backfill_evse_for_legacy_chargers

Populate evse table for Charger-001 and Charger-002 (created before the evse table existed).
Each gets one EVSE row with evse_id=1 to match current runtime behaviour.

Revision ID: h2b3c4d5e6f7
Revises: g1a2b3c4d5e6
Create Date: 2026-02-08

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "h2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "g1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Insert one EVSE (evse_id=1) per legacy charger that has no EVSE rows."""
    conn = op.get_bind()
    # Chargers that have no evse rows (legacy Charger-001, Charger-002, or any other).
    result = conn.execute(
        sa.text(
            "SELECT c.id FROM charger c "
            "WHERE NOT EXISTS (SELECT 1 FROM evse e WHERE e.charger_id = c.id)"
        )
    )
    rows = result.fetchall()
    for (charger_id,) in rows:
        conn.execute(
            sa.text("INSERT INTO evse (id, charger_id, evse_id) VALUES (:id, :charger_id, 1)"),
            {"id": str(uuid.uuid4()), "charger_id": charger_id},
        )


def downgrade() -> None:
    """Remove EVSE rows that were added for legacy Charger-001 and Charger-002."""
    conn = op.get_bind()
    # Delete the single EVSE we added for those two chargers (they have exactly one EVSE each).
    conn.execute(
        sa.text(
            "DELETE FROM evse WHERE charger_id IN ("
            "SELECT c.id FROM charger c "
            "WHERE c.charge_point_id IN ('Charger-001', 'Charger-002') "
            "AND (SELECT COUNT(*) FROM evse e WHERE e.charger_id = c.id) = 1"
            ")"
        )
    )
