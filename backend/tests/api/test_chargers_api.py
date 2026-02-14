"""API tests: chargers endpoints."""
import uuid

import pytest

from repositories.location_repository import create_location

pytestmark = pytest.mark.api

CP_ID = "CP-001"


@pytest.fixture
def location(db_session):
    """Create a location for charger tests (unique id per test)."""
    loc_id = f"loc-charger-{uuid.uuid4().hex[:8]}"
    return create_location(db_session, "Charger Test Location", "1 Test St", loc_id)


@pytest.fixture
def loc_id(location):
    """Location id from location fixture."""
    return location.id


def test_list_chargers_unknown_location_404(client):
    """GET /api/locations/{id}/chargers returns 404 for unknown location."""
    r = client.get(f"/api/locations/unknown-loc/chargers")
    assert r.status_code == 404


def test_list_chargers_empty(client, location, loc_id):
    """GET /api/locations/{id}/chargers returns 200 and empty list when no chargers."""
    r = client.get(f"/api/locations/{loc_id}/chargers")
    assert r.status_code == 200
    assert r.json() == []


def test_list_chargers_includes_db_only_charger(client, location, loc_id, db_session):
    """GET /api/locations/{id}/chargers returns charger from DB even when not in store (evse_count=0, connected=False)."""
    from repositories.charger_repository import create_charger as repo_create_charger
    repo_create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-DB-ONLY",
        connection_url="ws://x/ocpp",
        charger_name="DB Only",
    )
    r = client.get(f"/api/locations/{loc_id}/chargers")
    assert r.status_code == 200
    data = r.json()
    cp = next((c for c in data if c["charge_point_id"] == "CP-DB-ONLY"), None)
    assert cp is not None
    assert cp["evse_count"] == 0
    assert cp["connected"] is False


def test_create_charger_success(client, location, loc_id):
    """POST /api/locations/{id}/chargers returns 201 and charger summary."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Test Charger",
        "ocpp_version": "1.6",
        "evse_count": 2,
    }
    r = client.post(f"/api/locations/{loc_id}/chargers", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["charge_point_id"] == CP_ID
    assert data["charger_name"] == "Test Charger"
    assert data["evse_count"] == 2
    assert data["location_id"] == loc_id


def test_create_charger_unknown_location_404(client):
    """POST /api/locations/{id}/chargers returns 404 for unknown location."""
    body = {
        "connection_url": "ws://x/ocpp",
        "charge_point_id": "CP-X",
        "charger_name": "X",
        "ocpp_version": "1.6",
    }
    r = client.post("/api/locations/unknown-loc/chargers", json=body)
    assert r.status_code == 404


def test_create_charger_duplicate_409(client, location, loc_id):
    """POST /api/locations/{id}/chargers returns 409 when charge_point_id already exists."""
    body = {
        "connection_url": "ws://a/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "First",
        "ocpp_version": "1.6",
    }
    r1 = client.post(f"/api/locations/{loc_id}/chargers", json=body)
    assert r1.status_code == 201
    r2 = client.post(f"/api/locations/{loc_id}/chargers", json=body)
    assert r2.status_code == 409


def test_get_charger_404(client):
    """GET /api/chargers/{id} returns 404 for unknown charger."""
    r = client.get("/api/chargers/CP-NONE")
    assert r.status_code == 404


def test_get_charger_success(client, location, loc_id):
    """GET /api/chargers/{id} returns 200 and charger detail after create."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Detail Charger",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.get(f"/api/chargers/{CP_ID}")
    assert r.status_code == 200
    data = r.json()
    assert data["charge_point_id"] == CP_ID
    assert "evses" in data
    assert "config" in data


def test_get_charger_hydrates_from_db_when_not_in_store(client, location, loc_id, db_session):
    """GET /api/chargers/{id} hydrates charger from DB when not in store (evse_count from DB)."""
    from repositories.charger_repository import create_charger as repo_create_charger
    repo_create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-HYDRATE",
        connection_url="ws://x/ocpp",
        charger_name="Hydrate Me",
        evse_count=2,
    )
    r = client.get("/api/chargers/CP-HYDRATE")
    assert r.status_code == 200
    data = r.json()
    assert data["charge_point_id"] == "CP-HYDRATE"
    assert len(data["evses"]) == 2


def test_update_charger_config_success(client, location, loc_id):
    """PATCH /api/chargers/{id}/config returns 200 and updated config."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Config Charger",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.patch(f"/api/chargers/{CP_ID}/config", json={"HeartbeatInterval": 60})
    assert r.status_code == 200
    assert r.json()["config"].get("HeartbeatInterval") == 60


def test_update_charger_config_404(client):
    """PATCH /api/chargers/{id}/config returns 404 for unknown charger."""
    r = client.patch("/api/chargers/CP-NONE/config", json={"HeartbeatInterval": 60})
    assert r.status_code == 404


def test_update_charger_config_empty_body_returns_current(client, location, loc_id):
    """PATCH /api/chargers/{id}/config with empty body returns 200 and current detail (no changes)."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Config Charger",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.patch(f"/api/chargers/{CP_ID}/config", json={})
    assert r.status_code == 200
    assert r.json()["charge_point_id"] == CP_ID


def test_update_charger_success(client, location, loc_id):
    """PATCH /api/chargers/{id} returns 200 and updated metadata."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Original",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.patch(
        f"/api/chargers/{CP_ID}",
        json={"charger_name": "Updated Name", "connection_url": "ws://other/ocpp"},
    )
    assert r.status_code == 200
    assert r.json()["charger_name"] == "Updated Name"


def test_update_charger_404(client):
    """PATCH /api/chargers/{id} returns 404 for unknown charger."""
    r = client.patch("/api/chargers/CP-NONE", json={"charger_name": "X"})
    assert r.status_code == 404


def test_update_charger_when_not_in_store(client, location, loc_id, db_session):
    """PATCH /api/chargers/{id} when charger is in DB but not in store returns 200 (builds detail from row)."""
    from repositories.charger_repository import create_charger as repo_create_charger
    repo_create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-NOT-IN-STORE",
        connection_url="ws://x/ocpp",
        charger_name="Original",
    )
    r = client.patch(
        "/api/chargers/CP-NOT-IN-STORE",
        json={"charger_name": "Updated From Row"},
    )
    assert r.status_code == 200
    assert r.json()["charger_name"] == "Updated From Row"


def test_get_charger_logs_success(client, location, loc_id):
    """GET /api/chargers/{id}/logs returns 200 and list (possibly empty)."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Log Charger",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.get(f"/api/chargers/{CP_ID}/logs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_charger_logs_404(client):
    """GET /api/chargers/{id}/logs returns 404 for unknown charger."""
    r = client.get("/api/chargers/CP-NONE/logs")
    assert r.status_code == 404


def test_clear_charger_logs_success(client, location, loc_id):
    """DELETE /api/chargers/{id}/logs returns 204."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Log Charger",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.delete(f"/api/chargers/{CP_ID}/logs")
    assert r.status_code == 204


def test_clear_charger_logs_404(client):
    """DELETE /api/chargers/{id}/logs returns 404 for unknown charger."""
    r = client.delete("/api/chargers/CP-NONE/logs")
    assert r.status_code == 404


def test_delete_charger_success(client, location, loc_id):
    """DELETE /api/chargers/{id} returns 204 and charger is gone."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "To Delete",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.delete(f"/api/chargers/{CP_ID}")
    assert r.status_code == 204
    r2 = client.get(f"/api/chargers/{CP_ID}")
    assert r2.status_code == 404


def test_delete_charger_404(client):
    """DELETE /api/chargers/{id} returns 404 for unknown charger."""
    r = client.delete("/api/chargers/CP-NONE")
    assert r.status_code == 404


def test_connect_charger_202(client, location, loc_id):
    """POST /api/chargers/{id}/connect returns 202 (async connect)."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Connect Charger",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.post(f"/api/chargers/{CP_ID}/connect")
    assert r.status_code == 202


def test_connect_charger_404(client):
    """POST /api/chargers/{id}/connect returns 404 for unknown charger."""
    r = client.post("/api/chargers/CP-NONE/connect")
    assert r.status_code == 404


def test_connect_charger_basic_auth_no_password_400(client, location, loc_id, db_session):
    """POST /api/chargers/{id}/connect returns 400 when security_profile is basic but no password set."""
    from repositories.charger_repository import create_charger as repo_create_charger
    from repositories.charger_repository import update_charger as repo_update_charger
    repo_create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-BASIC-NO-PWD",
        connection_url="ws://x/ocpp",
        charger_name="Basic",
    )
    repo_update_charger(db_session, "CP-BASIC-NO-PWD", security_profile="basic")
    r = client.post("/api/chargers/CP-BASIC-NO-PWD/connect")
    assert r.status_code == 400
    assert "password" in r.json().get("detail", "").lower()


def test_disconnect_charger_204(client, location, loc_id):
    """POST /api/chargers/{id}/disconnect returns 204."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Disconnect Charger",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.post(f"/api/chargers/{CP_ID}/disconnect")
    assert r.status_code == 204


def test_disconnect_charger_404(client):
    """POST /api/chargers/{id}/disconnect returns 404 for unknown charger."""
    r = client.post("/api/chargers/CP-NONE/disconnect")
    assert r.status_code == 404


def test_start_transaction_404(client):
    """POST .../transactions/start returns 404 for unknown charger."""
    r = client.post(
        "/api/chargers/CP-NONE/transactions/start",
        json={"connector_id": 1, "id_tag": "TAG1"},
    )
    assert r.status_code == 404


def test_start_transaction_not_connected_400(client, location, loc_id):
    """POST .../transactions/start returns 400 when charger not connected to CSMS."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Tx Charger",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/start",
        json={"connector_id": 1, "id_tag": "TAG1"},
    )
    assert r.status_code == 400
    assert "not connected" in r.json().get("detail", "").lower()


def test_stop_transaction_404(client):
    """POST .../transactions/stop returns 404 for unknown charger."""
    r = client.post(
        "/api/chargers/CP-NONE/transactions/stop",
        json={"connector_id": 1},
    )
    assert r.status_code == 404


def test_stop_transaction_not_connected_400(client, location, loc_id):
    """POST .../transactions/stop returns 400 when charger not connected."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Tx Charger",
        "ocpp_version": "1.6",
    }
    client.post(f"/api/locations/{loc_id}/chargers", json=body)
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/stop",
        json={"connector_id": 1},
    )
    assert r.status_code == 400
    assert "not connected" in r.json().get("detail", "").lower()
