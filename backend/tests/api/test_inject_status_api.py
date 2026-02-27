"""API tests: POST /api/chargers/{charge_point_id}/inject_status endpoint."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from repositories.location_repository import create_location

pytestmark = pytest.mark.api

CP_ID = "CP-INJECT-TEST"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def location(db_session):
    loc_id = f"loc-inject-{uuid.uuid4().hex[:8]}"
    return create_location(db_session, "Inject Test Location", "1 Test St", loc_id)


@pytest.fixture
def loc_id(location):
    return location.id


@pytest.fixture
def charger_in_store(client, location, loc_id):
    """Create charger via API so it lands in the simulator store."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Inject Charger",
        "ocpp_version": "1.6",
        "evse_count": 2,
    }
    r = client.post(f"/api/locations/{loc_id}/chargers", json=body)
    assert r.status_code == 201
    return r.json()


def _attach_mock_client(cp_id: str) -> MagicMock:
    """Attach a mock OCPP client so sim.is_connected returns True."""
    from simulator_core.store import get_by_id as store_get
    sim = store_get(cp_id)
    assert sim is not None, f"Charger {cp_id} not in store"
    mock_conn = MagicMock()
    mock_conn.open = True
    mock_client = MagicMock()
    mock_client._connection = mock_conn
    mock_client.send_status_notification = AsyncMock(return_value=None)
    sim._ocpp_client = mock_client
    return mock_client


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_inject_status_unknown_charger_404(client):
    """Unknown charge_point_id → 404."""
    r = client.post(
        "/api/chargers/CP-DOES-NOT-EXIST/inject_status",
        json={"connector_id": 1, "status": "Available"},
    )
    assert r.status_code == 404


def test_inject_status_not_connected_400(client, charger_in_store):
    """Charger exists but has no OCPP client attached → 400 not connected."""
    r = client.post(
        f"/api/chargers/{CP_ID}/inject_status",
        json={"connector_id": 1, "status": "Unavailable"},
    )
    assert r.status_code == 400
    assert "not connected" in r.json()["detail"].lower()


def test_inject_status_connector_not_found_400(client, charger_in_store):
    """connector_id that doesn't exist on the charger → 400."""
    _attach_mock_client(CP_ID)
    r = client.post(
        f"/api/chargers/{CP_ID}/inject_status",
        json={"connector_id": 99, "status": "Available"},
    )
    assert r.status_code == 400
    assert "evse" in r.json()["detail"].lower()


def test_inject_status_invalid_transition_400(client, charger_in_store):
    """Available → Charging is not a valid OCPP 1.6 transition → 400."""
    _attach_mock_client(CP_ID)
    r = client.post(
        f"/api/chargers/{CP_ID}/inject_status",
        json={"connector_id": 1, "status": "Charging"},
    )
    assert r.status_code == 400
    assert "transition" in r.json()["detail"].lower()


def test_inject_status_faulted_missing_error_code_400(client, charger_in_store):
    """Faulted status without error_code field → 400."""
    _attach_mock_client(CP_ID)
    # Preparing → Faulted is a valid transition
    from simulator_core.store import get_by_id as store_get
    from simulator_core.evse import EvseState
    store_get(CP_ID).get_evse(1).state = EvseState.Preparing

    r = client.post(
        f"/api/chargers/{CP_ID}/inject_status",
        json={"connector_id": 1, "status": "Faulted"},
    )
    assert r.status_code == 400
    assert "error_code" in r.json()["detail"].lower()


def test_inject_status_faulted_no_error_value_400(client, charger_in_store):
    """Faulted status with error_code='NoError' → 400 (NoError not allowed with Faulted)."""
    _attach_mock_client(CP_ID)
    from simulator_core.store import get_by_id as store_get
    from simulator_core.evse import EvseState
    store_get(CP_ID).get_evse(1).state = EvseState.Preparing

    r = client.post(
        f"/api/chargers/{CP_ID}/inject_status",
        json={"connector_id": 1, "status": "Faulted", "error_code": "NoError"},
    )
    assert r.status_code == 400
    assert "error_code" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


def test_inject_status_success_204(client, charger_in_store):
    """Valid non-Faulted transition → 204, OCPP client called once."""
    mock_client = _attach_mock_client(CP_ID)

    r = client.post(
        f"/api/chargers/{CP_ID}/inject_status",
        json={"connector_id": 1, "status": "Unavailable"},
    )
    assert r.status_code == 204
    mock_client.send_status_notification.assert_awaited_once()


def test_inject_status_faulted_success_204(client, charger_in_store):
    """Faulted + valid error_code → 204; optional info and vendor_error_code accepted."""
    mock_client = _attach_mock_client(CP_ID)
    from simulator_core.store import get_by_id as store_get
    from simulator_core.evse import EvseState
    store_get(CP_ID).get_evse(1).state = EvseState.Preparing

    r = client.post(
        f"/api/chargers/{CP_ID}/inject_status",
        json={
            "connector_id": 1,
            "status": "Faulted",
            "error_code": "InternalError",
            "info": "test diagnostic info",
            "vendor_error_code": "E42",
        },
    )
    assert r.status_code == 204
    mock_client.send_status_notification.assert_awaited_once()


def test_inject_status_evse_state_updated(client, charger_in_store):
    """After successful injection, the EVSE state in the store reflects the new status."""
    _attach_mock_client(CP_ID)
    from simulator_core.store import get_by_id as store_get
    from simulator_core.evse import EvseState

    r = client.post(
        f"/api/chargers/{CP_ID}/inject_status",
        json={"connector_id": 1, "status": "Unavailable"},
    )
    assert r.status_code == 204
    assert store_get(CP_ID).get_evse(1).state == EvseState.Unavailable
