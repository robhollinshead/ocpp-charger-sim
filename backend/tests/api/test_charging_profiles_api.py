"""API tests for charging profile inspection endpoints."""
import uuid
from datetime import datetime, timezone

import pytest

from repositories.location_repository import create_location
from simulator_core.charging_profile import ChargingProfile, ChargingSchedulePeriod
from simulator_core.store import get_by_id as store_get

pytestmark = pytest.mark.api

CP_ID = "CP-PROFILES-TEST"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def location(db_session):
    loc_id = f"loc-profiles-{uuid.uuid4().hex[:8]}"
    return create_location(db_session, "Profile Test Location", "1 Test St", loc_id)


@pytest.fixture
def loc_id(location):
    return location.id


@pytest.fixture
def charger_in_store(client, location, loc_id):
    """Create charger via API so it lands in the simulator store."""
    body = {
        "connection_url": "ws://example.com/ocpp",
        "charge_point_id": CP_ID,
        "charger_name": "Profile Charger",
        "ocpp_version": "1.6",
        "evse_count": 2,
    }
    r = client.post(f"/api/locations/{loc_id}/chargers", json=body)
    assert r.status_code == 201
    return r.json()


@pytest.fixture(autouse=True)
def cleanup_store():
    """Clear injected profiles after each test."""
    yield
    sim = store_get(CP_ID)
    if sim is not None:
        sim._charging_profiles = []


def _inject_profile(
    cp_id: str = CP_ID,
    profile_id: int = 1,
    connector_id: int = 1,
    purpose: str = "TxDefaultProfile",
    limit_W: float = 22000.0,
) -> ChargingProfile:
    profile = ChargingProfile(
        charging_profile_id=profile_id,
        connector_id=connector_id,
        stack_level=0,
        charging_profile_purpose=purpose,
        charging_profile_kind="Absolute",
        charging_schedule_periods=[
            ChargingSchedulePeriod(0, limit_W, limit_W, "W")
        ],
        received_at=datetime.now(timezone.utc),
    )
    sim = store_get(cp_id)
    if sim is not None:
        sim._charging_profiles.append(profile)
    return profile


# ---------------------------------------------------------------------------
# List profiles
# ---------------------------------------------------------------------------


def test_list_profiles_empty(client, charger_in_store):
    r = client.get(f"/api/chargers/{CP_ID}/charging-profiles")
    assert r.status_code == 200
    assert r.json() == []


def test_list_profiles_returns_stored(client, charger_in_store):
    _inject_profile(profile_id=1, connector_id=1, limit_W=22000.0)
    _inject_profile(profile_id=2, connector_id=2, limit_W=11000.0)

    r = client.get(f"/api/chargers/{CP_ID}/charging-profiles")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2

    ids = {p["charging_profile_id"] for p in data}
    assert ids == {1, 2}

    # Check structure of one entry
    p1 = next(p for p in data if p["charging_profile_id"] == 1)
    assert p1["connector_id"] == 1
    assert p1["charging_profile_purpose"] == "TxDefaultProfile"
    assert p1["charging_profile_kind"] == "Absolute"
    assert p1["status"] == "Active"
    assert len(p1["charging_schedule_periods"]) == 1
    assert p1["charging_schedule_periods"][0]["limit_W"] == 22000.0


def test_list_profiles_unknown_charger_404(client):
    r = client.get("/api/chargers/NO-SUCH-CHARGER/charging-profiles")
    assert r.status_code == 404


def test_list_profiles_expired_profile_shows_expired_status(client, charger_in_store):
    profile = ChargingProfile(
        charging_profile_id=1, connector_id=1, stack_level=0,
        charging_profile_purpose="TxDefaultProfile",
        charging_profile_kind="Absolute",
        valid_to=datetime(2020, 1, 1, tzinfo=timezone.utc),  # past
        charging_schedule_periods=[ChargingSchedulePeriod(0, 22000.0, 22000.0, "W")],
        received_at=datetime.now(timezone.utc),
    )
    sim = store_get(CP_ID)
    sim._charging_profiles = [profile]

    r = client.get(f"/api/chargers/{CP_ID}/charging-profiles")
    assert r.status_code == 200
    data = r.json()
    assert data[0]["status"] == "Expired"
    assert data[0]["current_limit_W"] is None


def test_list_profiles_scheduled_profile_shows_scheduled_status(client, charger_in_store):
    from datetime import timedelta
    profile = ChargingProfile(
        charging_profile_id=1, connector_id=1, stack_level=0,
        charging_profile_purpose="TxDefaultProfile",
        charging_profile_kind="Absolute",
        valid_from=datetime.now(timezone.utc) + timedelta(hours=1),  # future
        charging_schedule_periods=[ChargingSchedulePeriod(0, 22000.0, 22000.0, "W")],
        received_at=datetime.now(timezone.utc),
    )
    sim = store_get(CP_ID)
    sim._charging_profiles = [profile]

    r = client.get(f"/api/chargers/{CP_ID}/charging-profiles")
    assert r.status_code == 200
    data = r.json()
    assert data[0]["status"] == "Scheduled"


# ---------------------------------------------------------------------------
# Evaluate endpoint
# ---------------------------------------------------------------------------


def test_evaluate_no_profiles_returns_null_limit(client, charger_in_store):
    r = client.get(f"/api/chargers/{CP_ID}/charging-profiles/evaluate?connector_id=1")
    assert r.status_code == 200
    data = r.json()
    assert data["limit_W"] is None
    assert data["effective_W"] == 0.0
    assert data["connector_id"] == 1


def test_evaluate_with_active_tx_default_profile(client, charger_in_store):
    _inject_profile(connector_id=1, limit_W=22000.0)

    r = client.get(f"/api/chargers/{CP_ID}/charging-profiles/evaluate?connector_id=1")
    assert r.status_code == 200
    data = r.json()
    assert data["limit_W"] == 22000.0
    assert data["effective_W"] == 22000.0
    assert data["purpose"] == "TxDefaultProfile"
    assert data["capped_by_max_profile"] is False


def test_evaluate_unknown_charger_404(client):
    r = client.get("/api/chargers/NO-SUCH/charging-profiles/evaluate?connector_id=1")
    assert r.status_code == 404
