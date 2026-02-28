"""API tests: scenario endpoints."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from repositories.location_repository import create_location
from repositories.vehicle_repository import create_vehicle
from simulator_core.scenario_engine import ScenarioRun, clear_all, set_active_scenario

from datetime import datetime, timezone

pytestmark = pytest.mark.api


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def location(db_session):
    loc_id = f"loc-scen-{uuid.uuid4().hex[:8]}"
    return create_location(db_session, "Scenario Test Location", "1 Scenario St", loc_id)


@pytest.fixture
def loc_id(location):
    return location.id


@pytest.fixture(autouse=True)
def reset_scenarios():
    """Clear in-memory scenario state before and after each test."""
    clear_all()
    yield
    clear_all()


def _running_run(location_id: str) -> ScenarioRun:
    return ScenarioRun(
        location_id=location_id,
        scenario_type="rush_period",
        duration_minutes=5,
        started_at=datetime.now(timezone.utc),
        total_pairs=3,
        completed_pairs=1,
        status="running",
    )


# ---------------------------------------------------------------------------
# POST /scenarios/rush-period
# ---------------------------------------------------------------------------

def test_start_rush_period_location_not_found(client):
    """POST returns 404 for unknown location."""
    r = client.post(
        "/api/locations/nonexistent-loc/scenarios/rush-period",
        json={"duration_minutes": 5},
    )
    assert r.status_code == 404


def test_start_rush_period_success(client, loc_id):
    """POST returns 202 and starts scenario in background."""
    # Patch run_rush_period so it doesn't actually run
    with patch("api.scenarios.run_rush_period", new=AsyncMock()) as mock_run, \
         patch("asyncio.create_task"):
        r = client.post(
            f"/api/locations/{loc_id}/scenarios/rush-period",
            json={"duration_minutes": 5},
        )
    assert r.status_code == 202
    data = r.json()
    assert data["location_id"] == loc_id
    assert data["scenario_type"] == "rush_period"
    assert data["duration_minutes"] == 5
    assert data["status"] == "running"


def test_start_rush_period_conflict_409(client, loc_id):
    """POST returns 409 if a scenario is already running."""
    set_active_scenario(loc_id, _running_run(loc_id))
    r = client.post(
        f"/api/locations/{loc_id}/scenarios/rush-period",
        json={"duration_minutes": 5},
    )
    assert r.status_code == 409


def test_start_rush_period_allows_restart_after_completion(client, loc_id):
    """POST succeeds if previous scenario is completed (not running)."""
    completed = _running_run(loc_id)
    completed.status = "completed"
    set_active_scenario(loc_id, completed)

    with patch("api.scenarios.run_rush_period", new=AsyncMock()), \
         patch("asyncio.create_task"):
        r = client.post(
            f"/api/locations/{loc_id}/scenarios/rush-period",
            json={"duration_minutes": 3},
        )
    assert r.status_code == 202


def test_start_rush_period_invalid_duration(client, loc_id):
    """POST returns 422 for duration < 1."""
    r = client.post(
        f"/api/locations/{loc_id}/scenarios/rush-period",
        json={"duration_minutes": 0},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /scenarios/active
# ---------------------------------------------------------------------------

def test_get_active_scenario_none(client, loc_id):
    """GET returns null when no scenario is active."""
    r = client.get(f"/api/locations/{loc_id}/scenarios/active")
    assert r.status_code == 200
    assert r.json() is None


def test_get_active_scenario_running(client, loc_id):
    """GET returns the running scenario."""
    set_active_scenario(loc_id, _running_run(loc_id))
    r = client.get(f"/api/locations/{loc_id}/scenarios/active")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "running"
    assert data["location_id"] == loc_id
    assert data["total_pairs"] == 3
    assert data["completed_pairs"] == 1


# ---------------------------------------------------------------------------
# DELETE /scenarios/active
# ---------------------------------------------------------------------------

def test_cancel_active_scenario(client, loc_id):
    """DELETE returns 204 and clears the scenario."""
    set_active_scenario(loc_id, _running_run(loc_id))
    r = client.delete(f"/api/locations/{loc_id}/scenarios/active")
    assert r.status_code == 204
    # Scenario should now be gone
    r2 = client.get(f"/api/locations/{loc_id}/scenarios/active")
    assert r2.json() is None


def test_cancel_when_no_active_scenario(client, loc_id):
    """DELETE is idempotent — no error when nothing is running."""
    r = client.delete(f"/api/locations/{loc_id}/scenarios/active")
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# POST /scenarios/stop-all-charging
# ---------------------------------------------------------------------------

def test_stop_all_charging_no_active_transactions(client, loc_id):
    """POST returns 200 with stopped=0 when no EVSEs have active transactions."""
    # No chargers in store for this location
    with patch("api.scenarios.store") as mock_store:
        mock_store.get_all.return_value = []
        r = client.post(f"/api/locations/{loc_id}/scenarios/stop-all-charging")
    assert r.status_code == 200
    data = r.json()
    assert data["stopped"] == 0
    assert data["errors"] == 0


def test_stop_all_charging_stops_active_evses(client, loc_id):
    """POST calls stop_transaction for each EVSE with an active transaction."""
    # Build fake charger with one active EVSE
    mock_evse = MagicMock()
    mock_evse.transaction_id = 42
    mock_evse.evse_id = 1

    mock_ocpp = AsyncMock()
    mock_ocpp.stop_transaction = AsyncMock()

    mock_sim = MagicMock()
    mock_sim.location_id = loc_id
    mock_sim.is_connected = True
    mock_sim.evses = [mock_evse]
    mock_sim._ocpp_client = mock_ocpp

    with patch("api.scenarios.store") as mock_store:
        mock_store.get_all.return_value = [mock_sim]
        r = client.post(f"/api/locations/{loc_id}/scenarios/stop-all-charging")

    assert r.status_code == 200
    data = r.json()
    assert data["stopped"] == 1
    assert data["errors"] == 0
    mock_ocpp.stop_transaction.assert_called_once_with(1)


def test_stop_all_charging_skips_disconnected_chargers(client, loc_id):
    """POST skips chargers that are not connected."""
    mock_evse = MagicMock()
    mock_evse.transaction_id = 1
    mock_evse.evse_id = 1

    mock_sim = MagicMock()
    mock_sim.location_id = loc_id
    mock_sim.is_connected = False
    mock_sim.evses = [mock_evse]

    with patch("api.scenarios.store") as mock_store:
        mock_store.get_all.return_value = [mock_sim]
        r = client.post(f"/api/locations/{loc_id}/scenarios/stop-all-charging")

    assert r.status_code == 200
    assert r.json()["stopped"] == 0


def test_stop_all_charging_counts_errors(client, loc_id):
    """POST counts errors when stop_transaction raises."""
    mock_evse = MagicMock()
    mock_evse.transaction_id = 1
    mock_evse.evse_id = 1

    mock_ocpp = AsyncMock()
    mock_ocpp.stop_transaction = AsyncMock(side_effect=RuntimeError("CSMS gone"))

    mock_sim = MagicMock()
    mock_sim.location_id = loc_id
    mock_sim.is_connected = True
    mock_sim.evses = [mock_evse]
    mock_sim._ocpp_client = mock_ocpp

    with patch("api.scenarios.store") as mock_store:
        mock_store.get_all.return_value = [mock_sim]
        r = client.post(f"/api/locations/{loc_id}/scenarios/stop-all-charging")

    assert r.status_code == 200
    data = r.json()
    assert data["stopped"] == 0
    assert data["errors"] == 1
