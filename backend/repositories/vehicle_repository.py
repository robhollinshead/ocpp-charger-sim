"""Vehicle repository: list, get, create, delete."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from models.vehicle import Vehicle
from models.vehicle_id_tag import VehicleIdTag


def create_vehicle(
    session: Session,
    *,
    location_id: str,
    name: str,
    id_tags: list[str],
    battery_capacity_kwh: float,
) -> Vehicle:
    """Create a vehicle with one or more idTags, commit, and return it."""
    vehicle = Vehicle(
        location_id=location_id,
        name=name,
        battery_capacity_kwh=battery_capacity_kwh,
    )
    session.add(vehicle)
    session.flush()
    for tag in id_tags:
        session.add(VehicleIdTag(vehicle_id=vehicle.id, id_tag=tag))
    session.commit()
    session.refresh(vehicle)
    return vehicle


def get_vehicle_by_id(session: Session, vehicle_id: str) -> Optional[Vehicle]:
    """Return vehicle by id or None."""
    return session.get(Vehicle, vehicle_id)


def get_vehicle_by_id_tag(session: Session, id_tag: str) -> Optional[Vehicle]:
    """Return vehicle that has this idTag, or None."""
    return session.execute(
        select(Vehicle).join(VehicleIdTag).where(VehicleIdTag.id_tag == id_tag)
    ).scalar_one_or_none()


def get_vehicle_by_name(session: Session, name: str) -> Optional[Vehicle]:
    """Return vehicle by name or None."""
    return session.execute(
        select(Vehicle).where(Vehicle.name == name)
    ).scalar_one_or_none()


def list_vehicles_by_location(session: Session, location_id: str) -> list[Vehicle]:
    """Return all vehicles for a location, with id_tags loaded."""
    result = session.execute(
        select(Vehicle)
        .where(Vehicle.location_id == location_id)
        .order_by(Vehicle.name)
        .options(selectinload(Vehicle.id_tags))
    )
    return list(result.scalars().all())


def delete_vehicle(session: Session, vehicle_id: str) -> bool:
    """Delete vehicle by id. Returns True if deleted, False if not found."""
    vehicle = get_vehicle_by_id(session, vehicle_id)
    if vehicle is None:
        return False
    session.delete(vehicle)
    session.commit()
    return True
