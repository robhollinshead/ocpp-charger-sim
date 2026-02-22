"""Unit tests: meter_engine (build_meter_values_payload, update_evse_meter, start_metering_loop)."""
import asyncio
import math

import pytest

from simulator_core.dc_voltage import get_pack_voltage_V
from simulator_core.evse import EVSE, EvseState, AC_GRID_VOLTAGE_V, SQRT3
from simulator_core.meter_engine import (
    build_meter_values_payload,
    start_metering_loop,
    update_evse_meter,
)

pytestmark = pytest.mark.unit


def test_build_meter_values_payload():
    """build_meter_values_payload returns OCPP-shaped dict with connectorId, transactionId, meterValue."""
    evse = EVSE(evse_id=1, max_power_W=22000.0)
    evse.transaction_id = 42
    evse.energy_Wh = 1000.0
    evse.power_W = 11000.0
    evse.current_A = 47.8
    evse.soc_pct = 25.0
    payload = build_meter_values_payload(evse)
    assert payload["connectorId"] == 1
    assert payload["transactionId"] == 42
    assert "meterValue" in payload
    assert len(payload["meterValue"]) == 1
    sampled = payload["meterValue"][0]["sampledValue"]
    values = {s["measurand"]: s["value"] for s in sampled}
    assert "Energy.Active.Import.Register" in values
    assert "Power.Active.Import" in values
    assert "SoC" in values


def test_update_evse_meter():
    """update_evse_meter updates power_W, energy_Wh, current_A, soc_pct."""
    evse = EVSE(evse_id=1, max_power_W=22000.0)
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse._initial_energy_Wh = 0.0
    evse.energy_Wh = 0.0
    evse.start_soc_pct = 20.0
    evse.battery_capacity_Wh = 100_000.0
    evse.offered_limit_W = 11000.0
    update_evse_meter(evse, dt_s=3600.0)
    assert evse.power_W == 11000.0
    assert evse.energy_Wh > 0
    assert evse.current_A > 0
    assert evse.soc_pct >= 20.0


def test_update_evse_meter_voltage_from_soc():
    """Voltage is computed from SOC using the sigmoid OCV model."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse.soc_pct = 20.0
    evse.offered_limit_W = 11000.0
    update_evse_meter(evse, dt_s=60.0)
    expected_voltage = get_pack_voltage_V(evse.soc_pct)
    assert expected_voltage > 0
    expected_current = 11000.0 / expected_voltage
    assert abs(evse.current_A - expected_current) < 0.01
    assert evse.power_W == 11000.0


@pytest.mark.asyncio
async def test_start_metering_loop_sends_once_then_stops():
    """start_metering_loop runs until stop_event; callback receives payload."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse.offered_limit_W = 11000.0
    received = []

    async def send_cb(payload):
        received.append(payload)

    task, stop_event = start_metering_loop(evse, send_cb, interval_s=0.05)
    await asyncio.sleep(0.06)
    stop_event.set()
    await asyncio.wait_for(task, timeout=1.0)
    assert len(received) >= 1
    assert received[0]["connectorId"] == 1
    assert "meterValue" in received[0]


# --- AC Charger Tests ---


def test_build_meter_values_payload_ac_excludes_soc():
    """AC chargers should not include SoC in MeterValues payload."""
    evse = EVSE(evse_id=1, max_power_W=22000.0, power_type="AC")
    evse.transaction_id = 42
    evse.energy_Wh = 1000.0
    evse.power_W = 11000.0
    evse.current_A = 15.9
    evse.soc_pct = 25.0  # Calculated internally but not sent
    payload = build_meter_values_payload(evse, power_type="AC")
    sampled = payload["meterValue"][0]["sampledValue"]
    measurands = {s["measurand"] for s in sampled}
    assert "Energy.Active.Import.Register" in measurands
    assert "Power.Active.Import" in measurands
    assert "Current.Import" in measurands
    assert "SoC" not in measurands


def test_build_meter_values_payload_dc_includes_soc():
    """DC chargers should include SoC in MeterValues payload."""
    evse = EVSE(evse_id=1, max_power_W=150000.0, power_type="DC")
    evse.transaction_id = 42
    evse.energy_Wh = 5000.0
    evse.power_W = 50000.0
    evse.current_A = 115.0
    evse.soc_pct = 30.0
    payload = build_meter_values_payload(evse, power_type="DC")
    sampled = payload["meterValue"][0]["sampledValue"]
    measurands = {s["measurand"] for s in sampled}
    assert "SoC" in measurands


def test_update_evse_meter_ac_current_calculation():
    """AC charger current should be calculated using 3-phase formula: I = P / (sqrt(3) * 400)."""
    evse = EVSE(evse_id=1, max_power_W=22000.0, power_type="AC")
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse._initial_energy_Wh = 0.0
    evse.energy_Wh = 0.0
    evse.start_soc_pct = 20.0
    evse.battery_capacity_Wh = 100_000.0
    evse.offered_limit_W = 22000.0  # 22 kW 3-phase AC
    update_evse_meter(evse, dt_s=3600.0)
    # Expected current: 22000 / (sqrt(3) * 400) ≈ 31.75 A
    expected_current = 22000.0 / (SQRT3 * AC_GRID_VOLTAGE_V)
    assert abs(evse.current_A - expected_current) < 0.01
    assert evse.power_W == 22000.0


def test_update_evse_meter_ac_voltage_fixed():
    """AC charger voltage should always return fixed 400V grid voltage."""
    evse = EVSE(evse_id=1, max_power_W=22000.0, power_type="AC")
    evse.soc_pct = 20.0
    assert evse.get_voltage_V() == AC_GRID_VOLTAGE_V
    evse.soc_pct = 80.0
    assert evse.get_voltage_V() == AC_GRID_VOLTAGE_V


def test_update_evse_meter_dc_voltage_varies_with_soc():
    """DC charger voltage should vary with SoC using OCV model."""
    evse = EVSE(evse_id=1, max_power_W=150000.0, power_type="DC")
    evse.soc_pct = 20.0
    voltage_low = evse.get_voltage_V()
    evse.soc_pct = 80.0
    voltage_high = evse.get_voltage_V()
    assert voltage_high > voltage_low  # Higher SoC = higher voltage


def test_get_effective_power_w_zero_when_suspended_ev():
    """get_effective_power_W returns 0 when state is SuspendedEV even if offered_limit_W > 0."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.SuspendedEV
    evse.offered_limit_W = 11000.0
    assert evse.get_effective_power_W() == 0.0


def test_get_effective_power_w_zero_when_suspended_evse():
    """get_effective_power_W returns 0 when state is SuspendedEVSE even if offered_limit_W > 0."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.SuspendedEVSE
    evse.offered_limit_W = 11000.0
    assert evse.get_effective_power_W() == 0.0


def test_get_effective_power_w_returns_offered_when_charging():
    """get_effective_power_W returns offered_limit_W when state is Charging."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.Charging
    evse.offered_limit_W = 11000.0
    assert evse.get_effective_power_W() == 11000.0


def test_evse_ac_power_conversion():
    """Test AC power/current conversion methods on EVSE."""
    evse = EVSE(evse_id=1, power_type="AC")
    # 32A * sqrt(3) * 400V ≈ 22.17 kW
    power = evse.ac_current_to_power_W(32.0)
    assert abs(power - 32.0 * SQRT3 * AC_GRID_VOLTAGE_V) < 0.01
    # Reverse: 22000W -> ~31.75A
    current = evse.ac_power_to_current_A(22000.0)
    expected = 22000.0 / (SQRT3 * AC_GRID_VOLTAGE_V)
    assert abs(current - expected) < 0.01


@pytest.mark.asyncio
async def test_start_metering_loop_ac_excludes_soc():
    """AC metering loop should produce payloads without SoC."""
    evse = EVSE(evse_id=1, power_type="AC")
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse.offered_limit_W = 11000.0
    received = []

    async def send_cb(payload):
        received.append(payload)

    task, stop_event = start_metering_loop(evse, send_cb, interval_s=0.05, power_type="AC")
    await asyncio.sleep(0.06)
    stop_event.set()
    await asyncio.wait_for(task, timeout=1.0)
    assert len(received) >= 1
    sampled = received[0]["meterValue"][0]["sampledValue"]
    measurands = {s["measurand"] for s in sampled}
    assert "SoC" not in measurands


def _power_from_payload(payload):
    """Extract Power.Active.Import value (string) from meter payload."""
    for s in payload["meterValue"][0]["sampledValue"]:
        if s.get("measurand") == "Power.Active.Import":
            return s["value"]
    return None


@pytest.mark.asyncio
async def test_start_metering_loop_calls_on_soc_full_once_and_continues_with_zero_power():
    """When SoC reaches 100%, on_soc_full is called once; loop continues and later payloads have 0 power."""
    evse = EVSE(evse_id=1, power_type="DC")
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse._initial_energy_Wh = 990.0
    evse.energy_Wh = 990.0
    evse.start_soc_pct = 99.0
    evse.battery_capacity_Wh = 1000.0
    evse.offered_limit_W = 40000.0  # one 1s tick adds ~11.1 Wh -> 100% SoC
    received = []
    on_soc_full_called = []

    async def send_cb(payload):
        received.append(payload)

    async def on_soc_full():
        on_soc_full_called.append(1)
        evse.transition_to(EvseState.SuspendedEV)

    task, stop_event = start_metering_loop(
        evse, send_cb, interval_s=1.0, power_type="DC", on_soc_full=on_soc_full
    )
    await asyncio.sleep(3.5)  # allow a few ticks: first hits 100% and calls on_soc_full, then more with 0 power
    stop_event.set()
    await asyncio.wait_for(task, timeout=2.0)
    assert len(on_soc_full_called) == 1
    assert evse.state == EvseState.SuspendedEV
    assert len(received) >= 2
    # Later payloads should have 0 power (loop continued after transition)
    later_powers = [_power_from_payload(p) for p in received[1:]]
    assert all(p == "0" for p in later_powers)


@pytest.mark.asyncio
async def test_start_metering_loop_without_on_soc_full_continues_at_100_soc():
    """Without on_soc_full, loop keeps running at 100% SoC and does not transition state."""
    evse = EVSE(evse_id=1, power_type="DC")
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse._initial_energy_Wh = 990.0
    evse.energy_Wh = 990.0
    evse.start_soc_pct = 99.0
    evse.battery_capacity_Wh = 1000.0
    evse.offered_limit_W = 40000.0
    received = []

    async def send_cb(payload):
        received.append(payload)

    task, stop_event = start_metering_loop(evse, send_cb, interval_s=1.0, power_type="DC")
    await asyncio.sleep(2.5)
    stop_event.set()
    await asyncio.wait_for(task, timeout=2.0)
    assert evse.state == EvseState.Charging
    assert len(received) >= 2
    # All payloads should show 100% SoC (SoC in payload for DC)
    for p in received:
        for s in p["meterValue"][0]["sampledValue"]:
            if s.get("measurand") == "SoC":
                assert s["value"] in ("100", "100.0")
                break
