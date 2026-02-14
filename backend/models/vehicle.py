"""Vehicle model for DB persistence."""
import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base


class Vehicle(Base):
    """Vehicle table: id, name, battery_capacity_kWh, location_id. idTags in vehicle_id_tag."""

    __tablename__ = "vehicle"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    battery_capacity_kwh: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    location_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("location.id", ondelete="CASCADE"),
        nullable=False,
    )

    id_tags: Mapped[list["VehicleIdTag"]] = relationship(
        "VehicleIdTag",
        back_populates="vehicle",
        cascade="all, delete-orphan",
    )
