"""VehicleIdTag model: many idTags per vehicle."""
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base


class VehicleIdTag(Base):
    """vehicle_id_tag table: one row per idTag per vehicle; id_tag is globally unique."""

    __tablename__ = "vehicle_id_tag"

    vehicle_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vehicle.id", ondelete="CASCADE"),
        primary_key=True,
    )
    id_tag: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, primary_key=True)

    vehicle: Mapped["Vehicle"] = relationship("Vehicle", back_populates="id_tags")
