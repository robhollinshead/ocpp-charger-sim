"""Charger model for DB persistence."""
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from models import Base


class Charger(Base):
    """Charger table: id, location_id, charge_point_id, connection_url, charger_name, ocpp_version, identity, config."""

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
    # BootNotification identity (set at creation, not editable). Backfilled in migration.
    charge_point_vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    charge_point_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # OCPP configuration (editable). Backfilled in migration.
    config: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    # OCPP 1.6 security profile: "none" (default), "basic" (username + password), later "basic_tls".
    security_profile: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    # Password for Basic auth (username = charge_point_id). Stored when security_profile is "basic"; never returned in API.
    basic_auth_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Power type: "AC" (3-phase grid) or "DC" (battery pack). Fixed at creation.
    power_type: Mapped[str] = mapped_column(String(4), nullable=False, default="DC")
