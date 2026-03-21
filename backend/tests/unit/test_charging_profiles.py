"""Unit tests for SetChargingProfile and ClearChargingProfile OCPP handlers."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from simulator_core.charger import Charger
from simulator_core.charging_profile import ChargingProfile, ChargingSchedulePeriod
from simulator_core.evse import EVSE, EvseState
from simulator_core.ocpp_client import SimulatorChargePoint

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_charger(power_type: str = "AC") -> Charger:
    evse = EVSE(evse_id=1)
    charger = Charger(
        charge_point_id="TEST-001",
        evses=[evse],
        power_type=power_type,
    )
    return charger


def _make_cp(charger: Charger) -> SimulatorChargePoint:
    """Create a SimulatorChargePoint without a real WebSocket connection."""
    cp = SimulatorChargePoint.__new__(SimulatorChargePoint)
    cp._charger = charger
    cp._connection = None
    # Stub send_status_notification so we don't need a real WS
    cp.send_status_notification = AsyncMock()
    return cp


def _set_profile_payload(
    profile_id: int = 1,
    connector_id: int = 1,
    stack_level: int = 0,
    purpose: str = "TxDefaultProfile",
    kind: str = "Absolute",
    limit: float = 22000.0,
    unit: str = "W",
    transaction_id: int | None = None,
    valid_to: str | None = None,
) -> tuple[int, dict]:
    """Return (connector_id, cs_charging_profiles) as expected by on_set_charging_profile."""
    profile = {
        "chargingProfileId": profile_id,
        "stackLevel": stack_level,
        "chargingProfilePurpose": purpose,
        "chargingProfileKind": kind,
        "chargingSchedule": {
            "chargingRateUnit": unit,
            "chargingSchedulePeriod": [{"startPeriod": 0, "limit": limit}],
        },
    }
    if transaction_id is not None:
        profile["transactionId"] = transaction_id
    if valid_to is not None:
        profile["validTo"] = valid_to
    return connector_id, profile


# ---------------------------------------------------------------------------
# SetChargingProfile
# ---------------------------------------------------------------------------


async def test_set_stores_profile():
    charger = _make_charger()
    cp = _make_cp(charger)
    with patch("asyncio.create_task"):
        conn_id, raw = _set_profile_payload()
        resp = await cp.on_set_charging_profile(conn_id, raw)
    assert resp.status.value == "Accepted"
    assert len(charger._charging_profiles) == 1
    assert charger._charging_profiles[0].charging_profile_id == 1


async def test_set_replaces_same_profile_id_and_connector():
    charger = _make_charger()
    cp = _make_cp(charger)
    with patch("asyncio.create_task"):
        # First profile: 22000 W
        await cp.on_set_charging_profile(*_set_profile_payload(limit=22000.0))
        assert len(charger._charging_profiles) == 1
        # Replace with 11000 W
        await cp.on_set_charging_profile(*_set_profile_payload(limit=11000.0))
    assert len(charger._charging_profiles) == 1
    assert charger._charging_profiles[0].charging_schedule_periods[0].limit_W == 11000.0


async def test_set_different_profile_ids_both_stored():
    charger = _make_charger()
    cp = _make_cp(charger)
    with patch("asyncio.create_task"):
        await cp.on_set_charging_profile(*_set_profile_payload(profile_id=1))
        await cp.on_set_charging_profile(*_set_profile_payload(profile_id=2))
    assert len(charger._charging_profiles) == 2


async def test_set_amps_to_watts_ac():
    """AC charger: limit in Amps should be converted using sqrt(3) * 400V."""
    import math
    charger = _make_charger(power_type="AC")
    cp = _make_cp(charger)
    with patch("asyncio.create_task"):
        await cp.on_set_charging_profile(*_set_profile_payload(limit=32.0, unit="A"))
    stored = charger._charging_profiles[0]
    expected_W = 32.0 * math.sqrt(3) * 400.0
    assert abs(stored.charging_schedule_periods[0].limit_W - expected_W) < 1.0
    assert stored.charging_schedule_periods[0].raw_unit == "A"
    assert stored.charging_schedule_periods[0].raw_limit == 32.0


async def test_set_amps_to_watts_dc():
    """DC charger: limit in Amps should be converted using pack voltage at 50% SoC."""
    from simulator_core.dc_voltage import get_pack_voltage_V
    charger = _make_charger(power_type="DC")
    cp = _make_cp(charger)
    with patch("asyncio.create_task"):
        await cp.on_set_charging_profile(*_set_profile_payload(limit=100.0, unit="A"))
    stored = charger._charging_profiles[0]
    expected_W = 100.0 * get_pack_voltage_V(50.0)
    assert abs(stored.charging_schedule_periods[0].limit_W - expected_W) < 1.0


async def test_set_no_periods_returns_rejected():
    charger = _make_charger()
    cp = _make_cp(charger)
    raw = {
        "chargingProfileId": 1, "stackLevel": 0,
        "chargingProfilePurpose": "TxDefaultProfile",
        "chargingProfileKind": "Absolute",
        "chargingSchedule": {"chargingRateUnit": "W", "chargingSchedulePeriod": []},
    }
    resp = await cp.on_set_charging_profile(1, raw)
    assert resp.status.value == "Rejected"
    assert len(charger._charging_profiles) == 0


async def test_set_missing_schedule_returns_rejected():
    charger = _make_charger()
    cp = _make_cp(charger)
    raw = {"chargingProfileId": 1, "stackLevel": 0,
           "chargingProfilePurpose": "TxDefaultProfile", "chargingProfileKind": "Absolute"}
    resp = await cp.on_set_charging_profile(1, raw)
    assert resp.status.value == "Rejected"


# ---------------------------------------------------------------------------
# ClearChargingProfile
# ---------------------------------------------------------------------------


def _inject_profiles(charger: Charger, *profiles: ChargingProfile) -> None:
    charger._charging_profiles = list(profiles)


def _simple_profile(
    profile_id: int = 1,
    connector_id: int = 1,
    purpose: str = "TxDefaultProfile",
    stack_level: int = 0,
) -> ChargingProfile:
    return ChargingProfile(
        charging_profile_id=profile_id,
        connector_id=connector_id,
        stack_level=stack_level,
        charging_profile_purpose=purpose,
        charging_profile_kind="Absolute",
        charging_schedule_periods=[
            ChargingSchedulePeriod(0, 11000.0, 11000.0, "W")
        ],
        received_at=datetime.now(timezone.utc),
    )


async def test_clear_by_id():
    charger = _make_charger()
    cp = _make_cp(charger)
    _inject_profiles(charger, _simple_profile(1), _simple_profile(2))
    with patch("asyncio.create_task"):
        resp = await cp.on_clear_charging_profile(id=1)
    assert resp.status.value == "Accepted"
    assert len(charger._charging_profiles) == 1
    assert charger._charging_profiles[0].charging_profile_id == 2


async def test_clear_by_connector():
    charger = _make_charger()
    cp = _make_cp(charger)
    _inject_profiles(charger, _simple_profile(1, connector_id=1), _simple_profile(2, connector_id=2))
    with patch("asyncio.create_task"):
        resp = await cp.on_clear_charging_profile(connector_id=1)
    assert resp.status.value == "Accepted"
    assert len(charger._charging_profiles) == 1
    assert charger._charging_profiles[0].connector_id == 2


async def test_clear_by_purpose():
    charger = _make_charger()
    cp = _make_cp(charger)
    _inject_profiles(
        charger,
        _simple_profile(1, purpose="TxDefaultProfile"),
        _simple_profile(2, purpose="TxProfile"),
    )
    with patch("asyncio.create_task"):
        resp = await cp.on_clear_charging_profile(
            charging_profile_purpose="TxDefaultProfile"
        )
    assert resp.status.value == "Accepted"
    assert len(charger._charging_profiles) == 1
    assert charger._charging_profiles[0].charging_profile_purpose == "TxProfile"


async def test_clear_by_stack_level():
    charger = _make_charger()
    cp = _make_cp(charger)
    _inject_profiles(
        charger,
        _simple_profile(1, stack_level=0),
        _simple_profile(2, stack_level=1),
    )
    with patch("asyncio.create_task"):
        resp = await cp.on_clear_charging_profile(stack_level=0)
    assert resp.status.value == "Accepted"
    assert len(charger._charging_profiles) == 1
    assert charger._charging_profiles[0].stack_level == 1


async def test_clear_no_match_returns_unknown():
    charger = _make_charger()
    cp = _make_cp(charger)
    _inject_profiles(charger, _simple_profile(1))
    resp = await cp.on_clear_charging_profile(id=99)
    assert resp.status.value == "Unknown"
    assert len(charger._charging_profiles) == 1


async def test_clear_no_criteria_removes_all():
    charger = _make_charger()
    cp = _make_cp(charger)
    _inject_profiles(charger, _simple_profile(1), _simple_profile(2), _simple_profile(3))
    with patch("asyncio.create_task"):
        resp = await cp.on_clear_charging_profile()
    assert resp.status.value == "Accepted"
    assert len(charger._charging_profiles) == 0


# ---------------------------------------------------------------------------
# Profile evaluation triggers SuspendedEVSE
# ---------------------------------------------------------------------------


async def test_no_profile_triggers_suspended_evse_via_meter_loop():
    """meter loop on_no_profile callback transitions to SuspendedEVSE."""
    from simulator_core.meter_engine import start_metering_loop

    charger = _make_charger()
    evse = charger.evses[0]
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse.session_start_time = datetime.now(timezone.utc).isoformat()
    evse.start_soc_pct = 20.0
    evse.battery_capacity_Wh = 100_000.0
    evse.soc_pct = 20.0

    # No profiles set → limit_fn returns None
    status_calls: list[EvseState] = []

    async def fake_status_notify(state: EvseState) -> None:
        status_calls.append(state)

    async def on_no_profile() -> None:
        evse.transition_to(EvseState.SuspendedEVSE)
        await fake_status_notify(EvseState.SuspendedEVSE)
        charger._meter_tasks.pop(1, None)

    async def send_cb(_payload: dict) -> None:
        pass

    limit_fn = lambda: charger.get_limit_W(1)  # noqa: E731

    task, stop_event = start_metering_loop(
        evse,
        send_cb,
        measurands=["Energy.Active.Import.Register"],
        interval_s=0.05,
        limit_fn=limit_fn,
        on_no_profile=on_no_profile,
    )
    charger._meter_tasks[1] = (task, stop_event)

    # Allow loop to tick
    await asyncio.sleep(0.15)
    stop_event.set()
    try:
        await asyncio.wait_for(task, timeout=1.0)
    except asyncio.CancelledError:
        pass

    assert evse.state == EvseState.SuspendedEVSE
    assert EvseState.SuspendedEVSE in status_calls


async def test_profile_arrival_resumes_suspended_evse():
    """After a profile arrives, _resume_evse_if_profile_available transitions to Charging."""
    charger = _make_charger()
    evse = charger.evses[0]
    evse.state = EvseState.SuspendedEVSE
    evse.transaction_id = 42
    evse.session_start_time = datetime.now(timezone.utc).isoformat()
    evse.start_soc_pct = 20.0
    evse.battery_capacity_Wh = 100_000.0
    evse.soc_pct = 20.0

    cp = _make_cp(charger)

    with patch("asyncio.create_task") as mock_create_task:
        mock_create_task.return_value = MagicMock()
        # Inject a profile manually so get_limit_W returns a value
        await cp.on_set_charging_profile(*_set_profile_payload(
            purpose="TxDefaultProfile", limit=22000.0,
        ))

    # The EVSE should have been transitioned back to Charging
    assert evse.state == EvseState.Charging
