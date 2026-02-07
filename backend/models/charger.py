"""Charger model for DB persistence."""
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class Charger(Base):
    """Charger table: id, location_id, charge_point_id, connection_url, charger_name, ocpp_version."""

    __tablename__ = "charger"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("location.id", ondelete="CASCADE"),
        nullable=False,
    )
    charge_point_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    connection_url: Mapped[str] = mapped_column(String(512), nullable=False)
    charger_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ocpp_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.6")
