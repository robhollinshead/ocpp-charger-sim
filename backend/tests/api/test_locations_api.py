"""API tests: locations endpoints using test DB (client fixture overrides get_db)."""
import pytest

from repositories.location_repository import create_location

pytestmark = pytest.mark.api


def test_list_locations_returns_list(client, db_session):
    """GET /api/locations returns 200 and a list (empty or existing locations)."""
    r = client.get("/api/locations")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_create_location_success(client, db_session):
    """POST /api/locations creates location and returns 201 with id, name, address, charger_count."""
    r = client.post(
        "/api/locations",
        json={"name": "New Location", "address": "1 New St"},
    )
    assert r.status_code == 201
    data = r.json()
    assert "id" in data
    assert data["name"] == "New Location"
    assert data["address"] == "1 New St"
    assert data["charger_count"] == 0


def test_create_location_then_list(client, db_session):
    """Create location via repository (same session as client), then GET /api/locations sees it."""
    create_location(db_session, "API Test Location", "123 API St", "loc-api-1")
    r = client.get("/api/locations")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    names = [loc["name"] for loc in data]
    assert "API Test Location" in names


def test_delete_location_success(client, db_session):
    """DELETE /api/locations/{id} returns 204 and location is removed."""
    create_location(db_session, "To Delete", "1 Del St", "loc-del-1")
    r = client.delete("/api/locations/loc-del-1")
    assert r.status_code == 204
    r2 = client.get("/api/locations")
    assert r2.status_code == 200
    ids = [loc["id"] for loc in r2.json()]
    assert "loc-del-1" not in ids


def test_delete_location_404(client):
    """DELETE /api/locations/{id} returns 404 for unknown id."""
    r = client.delete("/api/locations/unknown-loc")
    assert r.status_code == 404
