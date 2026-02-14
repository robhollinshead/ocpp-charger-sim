"""API tests: vehicles endpoints."""
import uuid

import pytest

from repositories.location_repository import create_location

pytestmark = pytest.mark.api

VEHICLE_NAME = "Test Vehicle"
ID_TAG = "TAG-V1"


@pytest.fixture
def location(db_session):
    """Create a location for vehicle tests (unique id per test)."""
    loc_id = f"loc-vehicle-{uuid.uuid4().hex[:8]}"
    return create_location(db_session, "Vehicle Test Location", "2 Test St", loc_id)


@pytest.fixture
def loc_id(location):
    """Location id from location fixture."""
    return location.id


def test_list_vehicles_unknown_location_404(client):
    """GET /api/locations/{id}/vehicles returns 404 for unknown location."""
    r = client.get("/api/locations/unknown-loc/vehicles")
    assert r.status_code == 404


def test_list_vehicles_empty(client, location, loc_id):
    """GET /api/locations/{id}/vehicles returns 200 and empty list when no vehicles."""
    r = client.get(f"/api/locations/{loc_id}/vehicles")
    assert r.status_code == 200
    assert r.json() == []


def test_create_vehicle_success(client, location, loc_id):
    """POST /api/locations/{id}/vehicles returns 201 and vehicle response."""
    body = {
        "name": VEHICLE_NAME,
        "idTags": [ID_TAG],
        "battery_capacity_kWh": 75.0,
    }
    r = client.post(f"/api/locations/{loc_id}/vehicles", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == VEHICLE_NAME
    assert ID_TAG in data["idTags"]
    assert data["battery_capacity_kWh"] == 75.0
    assert data["location_id"] == loc_id
    assert "id" in data


def test_create_vehicle_unknown_location_404(client):
    """POST /api/locations/{id}/vehicles returns 404 for unknown location."""
    body = {"name": "V1", "idTags": ["T1"], "battery_capacity_kWh": 50.0}
    r = client.post("/api/locations/unknown-loc/vehicles", json=body)
    assert r.status_code == 404


def test_create_vehicle_duplicate_name_409(client, location, loc_id):
    """POST /api/locations/{id}/vehicles returns 409 when name already exists."""
    body = {"name": VEHICLE_NAME, "idTags": [ID_TAG], "battery_capacity_kWh": 75.0}
    r1 = client.post(f"/api/locations/{loc_id}/vehicles", json=body)
    assert r1.status_code == 201
    body2 = {"name": VEHICLE_NAME, "idTags": ["OTHER-TAG"], "battery_capacity_kWh": 60.0}
    r2 = client.post(f"/api/locations/{loc_id}/vehicles", json=body2)
    assert r2.status_code == 409


def test_create_vehicle_duplicate_id_tag_409(client, location, loc_id):
    """POST /api/locations/{id}/vehicles returns 409 when idTag already exists."""
    body = {"name": VEHICLE_NAME, "idTags": [ID_TAG], "battery_capacity_kWh": 75.0}
    r1 = client.post(f"/api/locations/{loc_id}/vehicles", json=body)
    assert r1.status_code == 201
    body2 = {"name": "Other Vehicle", "idTags": [ID_TAG], "battery_capacity_kWh": 60.0}
    r2 = client.post(f"/api/locations/{loc_id}/vehicles", json=body2)
    assert r2.status_code == 409


def test_delete_vehicle_success(client, location, loc_id):
    """DELETE /api/locations/{id}/vehicles/{vehicle_id} returns 204."""
    body = {"name": VEHICLE_NAME, "idTags": [ID_TAG], "battery_capacity_kWh": 75.0}
    r_create = client.post(f"/api/locations/{loc_id}/vehicles", json=body)
    assert r_create.status_code == 201
    vehicle_id = r_create.json()["id"]
    r = client.delete(f"/api/locations/{loc_id}/vehicles/{vehicle_id}")
    assert r.status_code == 204
    r_list = client.get(f"/api/locations/{loc_id}/vehicles")
    assert r_list.status_code == 200
    ids = [v["id"] for v in r_list.json()]
    assert vehicle_id not in ids


def test_delete_vehicle_unknown_location_404(client, location, loc_id):
    """DELETE with wrong location returns 404."""
    body = {"name": VEHICLE_NAME, "idTags": [ID_TAG], "battery_capacity_kWh": 75.0}
    r_create = client.post(f"/api/locations/{loc_id}/vehicles", json=body)
    vehicle_id = r_create.json()["id"]
    r = client.delete(f"/api/locations/other-loc/vehicles/{vehicle_id}")
    assert r.status_code == 404


def test_delete_vehicle_not_found_404(client, location, loc_id):
    """DELETE with unknown vehicle_id returns 404."""
    r = client.delete(f"/api/locations/{loc_id}/vehicles/nonexistent-id")
    assert r.status_code == 404
