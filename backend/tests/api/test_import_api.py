"""API tests: import endpoints (CSV/JSON upload and templates)."""
import io
import uuid

import pytest

from repositories.location_repository import create_location

pytestmark = pytest.mark.api


@pytest.fixture
def location(db_session):
    """Create a location for import tests (unique id per test)."""
    loc_id = f"loc-import-{uuid.uuid4().hex[:8]}"
    return create_location(db_session, "Import Test Location", "3 Test St", loc_id)


@pytest.fixture
def loc_id(location):
    """Location id from location fixture."""
    return location.id


def test_import_chargers_unknown_location_404(client):
    """POST /api/locations/{id}/import/chargers returns 404 for unknown location."""
    data = {"file": ("chargers.csv", io.BytesIO(b"connection_url,charger_name,charge_point_id\nws://x/o,A01,CP-A01"), "text/csv")}
    r = client.post(f"/api/locations/unknown-loc/import/chargers", files=data)
    assert r.status_code == 404


def test_import_chargers_csv_success(client, location, loc_id):
    """POST /api/locations/{id}/import/chargers with valid CSV returns 200 and success list."""
    csv = b"connection_url,charger_name,charge_point_id,charge_point_vendor,charge_point_model,firmware_version,number_of_evses,ocpp_version\nws://example.com/ocpp,Imported Charger,CP-IMP,FastCharge,Pro 150,1.0,1,1.6\n"
    data = {"file": ("chargers.csv", io.BytesIO(csv), "text/csv")}
    r = client.post(f"/api/locations/{loc_id}/import/chargers", files=data)
    assert r.status_code == 200
    body = r.json()
    assert "success" in body and "failed" in body
    assert len(body["success"]) == 1
    assert body["success"][0]["charge_point_id"] == "CP-IMP"


def test_import_chargers_empty_file_400(client, location, loc_id):
    """POST /api/locations/{id}/import/chargers with empty file returns 400."""
    data = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    r = client.post(f"/api/locations/{loc_id}/import/chargers", files=data)
    assert r.status_code == 400


def test_import_vehicles_unknown_location_404(client):
    """POST /api/locations/{id}/import/vehicles returns 404 for unknown location."""
    csv = b"name,idTag,battery_capacity_kWh\nV1,TAG1,75\n"
    data = {"file": ("vehicles.csv", io.BytesIO(csv), "text/csv")}
    r = client.post("/api/locations/unknown-loc/import/vehicles", files=data)
    assert r.status_code == 404


def test_import_vehicles_csv_success(client, location, loc_id):
    """POST /api/locations/{id}/import/vehicles with valid CSV returns 200 and success list."""
    csv = b"name,idTag,battery_capacity_kWh\nImported Vehicle,IMP-TAG,80\n"
    data = {"file": ("vehicles.csv", io.BytesIO(csv), "text/csv")}
    r = client.post(f"/api/locations/{loc_id}/import/vehicles", files=data)
    assert r.status_code == 200
    body = r.json()
    assert "success" in body and "failed" in body
    assert len(body["success"]) == 1
    assert body["success"][0]["name"] == "Imported Vehicle"


def test_import_vehicles_empty_file_400(client, location, loc_id):
    """POST /api/locations/{id}/import/vehicles with empty file returns 400."""
    data = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    r = client.post(f"/api/locations/{loc_id}/import/vehicles", files=data)
    assert r.status_code == 400


def test_template_chargers_csv(client):
    """GET /api/import/templates/chargers.csv returns CSV template."""
    r = client.get("/api/import/templates/chargers.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert b"charge_point_id" in r.content or "charge_point_id" in r.text


def test_template_chargers_json(client):
    """GET /api/import/templates/chargers.json returns JSON template."""
    r = client.get("/api/import/templates/chargers.json")
    assert r.status_code == 200
    assert "application/json" in r.headers.get("content-type", "")
    data = r.json()
    assert isinstance(data, list)


def test_template_vehicles_csv(client):
    """GET /api/import/templates/vehicles.csv returns CSV template."""
    r = client.get("/api/import/templates/vehicles.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")


def test_template_vehicles_json(client):
    """GET /api/import/templates/vehicles.json returns JSON template."""
    r = client.get("/api/import/templates/vehicles.json")
    assert r.status_code == 200
    assert "application/json" in r.headers.get("content-type", "")
    data = r.json()
    assert isinstance(data, list)
