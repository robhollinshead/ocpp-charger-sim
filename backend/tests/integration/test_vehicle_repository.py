"""Integration tests: vehicle repository with test DB session."""
import pytest

from repositories.location_repository import create_location
from repositories.vehicle_repository import (
    create_vehicle,
    delete_vehicle,
    get_vehicle_by_id,
    get_vehicle_by_id_tag,
    get_vehicle_by_name,
    list_vehicles_by_location,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def loc_id(db_session):
    """Create a location and return its id (unique per test)."""
    import uuid
    lid = f"loc-repo-vehicle-{uuid.uuid4().hex[:8]}"
    loc = create_location(db_session, "Vehicle Repo Location", "2 Repo St", lid)
    return loc.id


def test_create_vehicle_and_get_by_id(db_session, loc_id):
    """create_vehicle then get_vehicle_by_id returns the vehicle."""
    vehicle = create_vehicle(
        db_session,
        location_id=loc_id,
        name="Repo Vehicle",
        id_tags=["TAG-R1", "TAG-R2"],
        battery_capacity_kwh=75.0,
    )
    assert vehicle.id is not None
    found = get_vehicle_by_id(db_session, vehicle.id)
    assert found is not None
    assert found.name == "Repo Vehicle"
    assert len(found.id_tags) >= 1


def test_get_vehicle_by_id_not_found(db_session):
    """get_vehicle_by_id returns None for unknown id."""
    assert get_vehicle_by_id(db_session, "nonexistent-id") is None


def test_get_vehicle_by_id_tag(db_session, loc_id):
    """get_vehicle_by_id_tag returns vehicle that has that tag."""
    create_vehicle(
        db_session,
        location_id=loc_id,
        name="Tag Vehicle",
        id_tags=["UNIQUE-TAG-123"],
        battery_capacity_kwh=60.0,
    )
    vehicle = get_vehicle_by_id_tag(db_session, "UNIQUE-TAG-123")
    assert vehicle is not None
    assert vehicle.name == "Tag Vehicle"


def test_get_vehicle_by_id_tag_not_found(db_session):
    """get_vehicle_by_id_tag returns None for unknown tag."""
    assert get_vehicle_by_id_tag(db_session, "UNKNOWN-TAG") is None


def test_get_vehicle_by_name(db_session, loc_id):
    """get_vehicle_by_name returns vehicle with that name."""
    create_vehicle(
        db_session,
        location_id=loc_id,
        name="Unique Name Vehicle",
        id_tags=["TAG-N"],
        battery_capacity_kwh=50.0,
    )
    vehicle = get_vehicle_by_name(db_session, "Unique Name Vehicle")
    assert vehicle is not None
    assert vehicle.name == "Unique Name Vehicle"


def test_get_vehicle_by_name_not_found(db_session):
    """get_vehicle_by_name returns None for unknown name."""
    assert get_vehicle_by_name(db_session, "No Such Name") is None


def test_list_vehicles_by_location(db_session, loc_id):
    """list_vehicles_by_location returns vehicles for that location."""
    create_vehicle(
        db_session,
        location_id=loc_id,
        name="List Vehicle 1",
        id_tags=["LV1"],
        battery_capacity_kwh=70.0,
    )
    create_vehicle(
        db_session,
        location_id=loc_id,
        name="List Vehicle 2",
        id_tags=["LV2"],
        battery_capacity_kwh=80.0,
    )
    vehicles = list_vehicles_by_location(db_session, loc_id)
    names = [v.name for v in vehicles]
    assert "List Vehicle 1" in names and "List Vehicle 2" in names


def test_delete_vehicle(db_session, loc_id):
    """delete_vehicle removes vehicle and returns True."""
    vehicle = create_vehicle(
        db_session,
        location_id=loc_id,
        name="To Delete Vehicle",
        id_tags=["TAG-DEL"],
        battery_capacity_kwh=65.0,
    )
    assert delete_vehicle(db_session, vehicle.id) is True
    assert get_vehicle_by_id(db_session, vehicle.id) is None


def test_delete_vehicle_not_found(db_session):
    """delete_vehicle returns False for unknown id."""
    assert delete_vehicle(db_session, "nonexistent-id") is False
