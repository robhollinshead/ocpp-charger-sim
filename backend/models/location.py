"""Location model for DB persistence."""
import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class Location(Base):
    """Location table: id, name, address, created_at."""

    __tablename__ = "location"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(512), nullable=False)
