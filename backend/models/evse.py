"""EVSE model for DB persistence."""
import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class Evse(Base):
    """EVSE table: id, charger_id, evse_id (connector index 1-10)."""

    __tablename__ = "evse"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    charger_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("charger.id", ondelete="CASCADE"),
        nullable=False,
    )
    evse_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("charger_id", "evse_id", name="uq_evse_charger_id_evse_id"),)
