"""Location repository: list, get, create."""
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.location import Location


def list_locations(session: Session) -> list[Location]:
    """Return all locations."""
    result = session.execute(select(Location).order_by(Location.name))
    return list(result.scalars().all())


def get_location(session: Session, location_id: str) -> Optional[Location]:
    """Return a location by id or None."""
    return session.get(Location, location_id)


def create_location(session: Session, name: str, address: str, location_id: str | None = None) -> Location:
    """Create a location, commit, and return it. Id is generated if not provided."""
    loc = Location(id=location_id or str(uuid.uuid4()), name=name, address=address)
    session.add(loc)
    session.commit()
    session.refresh(loc)
    return loc


def count_locations(session: Session) -> int:
    """Return the number of locations (for seeding)."""
    result = session.execute(select(func.count()).select_from(Location))
    return result.scalar() or 0


def delete_location(session: Session, location_id: str) -> bool:
    """Delete a location by id. Returns True if deleted, False if not found."""
    loc = get_location(session, location_id)
    if loc is None:
        return False
    session.delete(loc)
    session.commit()
    return True
