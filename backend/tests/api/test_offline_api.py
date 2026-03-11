"""API tests: offline mode endpoints — go-offline, go-online, and offline transaction support."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from repositories.location_repository import create_location
from simulator_core.charger import CachedMessage
from simulator_core.store import get_by_id as store_get

pytestmark = pytest.mark.api

CP_ID = "CP-OFFLINE-TEST"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def location(db_session):
    loc_id = f"loc-offline-{uuid.uuid4().hex[:8]}"
    return create_location(db_session, "Offline Test Location", "1 Test St", loc_id)


@pytest.fixture
def loc_id(location):
    return location.id


@pytest.fixture
def charger_in_store(client, location, loc_id):
    """Create charger via API so it lands in the simulator store."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Offline Charger",
        "ocpp_version": "1.6",
        "evse_count": 2,
    }
    r = client.post(f"/api/locations/{loc_id}/chargers", json=body)
    assert r.status_code == 201
    return r.json()


@pytest.fixture(autouse=True)
def cleanup_store():
    """Reset offline mode and cache on the charger after each test."""
    yield
    sim = store_get(CP_ID)
    if sim is not None:
        sim.set_online()
        sim.pop_message_cache()
        sim._ocpp_client = None


def _attach_mock_client(cp_id: str = CP_ID) -> MagicMock:
    """Attach a mock OCPP client so sim.is_connected returns True."""
    sim = store_get(cp_id)
    assert sim is not None
    mock_conn = MagicMock()
    mock_conn.open = True
    mock_conn.close = AsyncMock(return_value=None)  # close() is awaited in go_offline
    mock_client = MagicMock()
    mock_client._connection = mock_conn
    mock_client.send_status_notification = AsyncMock(return_value=None)
    mock_client.start_transaction = AsyncMock(return_value=1)
    mock_client.stop_transaction = AsyncMock(return_value=True)
    sim._ocpp_client = mock_client
    return mock_client


# ---------------------------------------------------------------------------
# go-offline
# ---------------------------------------------------------------------------


def test_go_offline_returns_204(client, charger_in_store):
    """go-offline closes connection and returns 204."""
    _attach_mock_client()
    r = client.post(f"/api/chargers/{CP_ID}/go-offline")
    assert r.status_code == 204
    sim = store_get(CP_ID)
    assert sim is not None
    assert sim.is_offline_mode()


def test_go_offline_idempotent_when_already_offline(client, charger_in_store):
    """Calling go-offline twice is safe and still returns 204."""
    _attach_mock_client()
    client.post(f"/api/chargers/{CP_ID}/go-offline")
    r = client.post(f"/api/chargers/{CP_ID}/go-offline")
    assert r.status_code == 204
    sim = store_get(CP_ID)
    assert sim.is_offline_mode()


def test_go_offline_404_unknown_charger(client):
    """Unknown charger returns 404."""
    r = client.post("/api/chargers/DOES-NOT-EXIST/go-offline")
    assert r.status_code == 404


def test_go_offline_when_not_connected(client, charger_in_store):
    """go-offline works even if charger is not connected (idempotent on WS side)."""
    # No client attached — not connected
    r = client.post(f"/api/chargers/{CP_ID}/go-offline")
    assert r.status_code == 204
    sim = store_get(CP_ID)
    assert sim.is_offline_mode()


# ---------------------------------------------------------------------------
# go-online
# ---------------------------------------------------------------------------


def test_go_online_returns_202(client, charger_in_store):
    """go-online returns 202 with status and cached_messages count."""
    sim = store_get(CP_ID)
    sim.set_offline()
    r = client.post(f"/api/chargers/{CP_ID}/go-online")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "going_online"
    assert "cached_messages" in body
    assert not sim.is_offline_mode()


def test_go_online_returns_cached_message_count(client, charger_in_store):
    """cached_messages count reflects messages cached during offline period."""
    sim = store_get(CP_ID)
    sim.set_offline()
    sim.cache_message(CachedMessage("StatusNotification", object(), 1, None, "ts"))
    sim.cache_message(CachedMessage("MeterValues", object(), 1, -1, "ts"))
    r = client.post(f"/api/chargers/{CP_ID}/go-online")
    assert r.status_code == 202
    assert r.json()["cached_messages"] == 2


def test_go_online_404_unknown_charger(client):
    """Unknown charger returns 404."""
    r = client.post("/api/chargers/DOES-NOT-EXIST/go-online")
    assert r.status_code == 404


def test_go_online_when_already_online(client, charger_in_store):
    """go-online is safe to call even if not in offline mode."""
    r = client.post(f"/api/chargers/{CP_ID}/go-online")
    assert r.status_code == 202


# ---------------------------------------------------------------------------
# ChargerDetail exposes offline state
# ---------------------------------------------------------------------------


def test_charger_detail_includes_offline_mode(client, charger_in_store):
    """GET /api/chargers/{id} includes offline_mode and cached_message_count."""
    r = client.get(f"/api/chargers/{CP_ID}")
    assert r.status_code == 200
    body = r.json()
    assert "offline_mode" in body
    assert "cached_message_count" in body
    assert body["offline_mode"] is False
    assert body["cached_message_count"] == 0


def test_charger_detail_reflects_offline_state(client, charger_in_store):
    """After go-offline, ChargerDetail shows offline_mode=True."""
    client.post(f"/api/chargers/{CP_ID}/go-offline")
    r = client.get(f"/api/chargers/{CP_ID}")
    assert r.status_code == 200
    assert r.json()["offline_mode"] is True


def test_charger_detail_shows_cached_message_count(client, charger_in_store):
    """After caching messages offline, ChargerDetail shows correct count."""
    sim = store_get(CP_ID)
    sim.set_offline()
    sim.cache_message(CachedMessage("MeterValues", object(), 1, -1, "ts"))
    sim.cache_message(CachedMessage("MeterValues", object(), 1, -1, "ts"))
    r = client.get(f"/api/chargers/{CP_ID}")
    assert r.json()["cached_message_count"] == 2


# ---------------------------------------------------------------------------
# start_transaction: allows offline mode
# ---------------------------------------------------------------------------


def test_start_transaction_blocked_when_disconnected_and_not_offline(client, charger_in_store):
    """start_transaction returns 400 if not connected AND not offline."""
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/start",
        json={"connector_id": 1, "id_tag": "TESTTAG"},
    )
    assert r.status_code == 400
    assert "not connected" in r.json()["detail"].lower()


def test_start_transaction_allowed_when_connected(client, charger_in_store):
    """start_transaction works normally when connected."""
    _attach_mock_client()
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/start",
        json={"connector_id": 1, "id_tag": "TESTTAG"},
    )
    assert r.status_code == 200
    assert "transaction_id" in r.json()


def test_start_transaction_allowed_when_offline(client, charger_in_store):
    """start_transaction allowed when charger is offline — uses local negative tx ID."""
    sim = store_get(CP_ID)
    sim.set_offline()
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/start",
        json={"connector_id": 1, "id_tag": "TESTTAG"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "transaction_id" in body
    # Local offline transaction IDs are negative
    assert body["transaction_id"] < 0


def test_start_transaction_caches_messages_when_offline(client, charger_in_store):
    """When offline, start_transaction caches StartTransaction and StatusNotifications."""
    sim = store_get(CP_ID)
    sim.set_offline()
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/start",
        json={"connector_id": 1, "id_tag": "TESTTAG"},
    )
    assert r.status_code == 200
    # Should have cached StartTransaction and StatusNotifications
    cached = sim.get_message_cache()
    msg_types = [m.message_type for m in cached]
    assert "StartTransaction" in msg_types
    assert "StatusNotification" in msg_types


# ---------------------------------------------------------------------------
# stop_transaction: allows offline mode
# ---------------------------------------------------------------------------


def test_stop_transaction_blocked_when_disconnected_and_not_offline(client, charger_in_store):
    """stop_transaction returns 400 if not connected AND not offline."""
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/stop",
        json={"connector_id": 1},
    )
    assert r.status_code == 400
    assert "not connected" in r.json()["detail"].lower()


def test_stop_transaction_allowed_when_offline(client, charger_in_store):
    """stop_transaction allowed when offline — caches StopTransaction."""
    sim = store_get(CP_ID)
    sim.set_offline()
    # Start an offline transaction first
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/start",
        json={"connector_id": 1, "id_tag": "TESTTAG"},
    )
    assert r.status_code == 200

    # Now stop it
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/stop",
        json={"connector_id": 1},
    )
    assert r.status_code == 204
    # StopTransaction should be in the cache
    cached = sim.get_message_cache()
    stop_msgs = [m for m in cached if m.message_type == "StopTransaction"]
    assert len(stop_msgs) == 1


def test_stop_transaction_offline_returns_404_when_no_active_tx(client, charger_in_store):
    """stop_transaction returns 400 when no active transaction (even in offline mode)."""
    sim = store_get(CP_ID)
    sim.set_offline()
    r = client.post(
        f"/api/chargers/{CP_ID}/transactions/stop",
        json={"connector_id": 1},
    )
    assert r.status_code == 400
    assert "no active transaction" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# TxDefaultPowerW config
# ---------------------------------------------------------------------------


def test_update_config_tx_default_power_w(client, charger_in_store):
    """PATCH /config accepts TxDefaultPowerW and propagates to EVSEs."""
    r = client.patch(
        f"/api/chargers/{CP_ID}/config",
        json={"TxDefaultPowerW": 11000.0},
    )
    assert r.status_code == 200
    sim = store_get(CP_ID)
    assert sim is not None
    assert sim.config.get("TxDefaultPowerW") == 11000.0
    for evse in sim.evses:
        assert evse.tx_default_power_W == 11000.0
