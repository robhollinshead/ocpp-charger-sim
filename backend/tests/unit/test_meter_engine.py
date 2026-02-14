"""Unit tests: meter_engine (build_meter_values_payload, update_evse_meter, start_metering_loop)."""
import asyncio

import pytest

from simulator_core.evse import EVSE, EvseState
from simulator_core.meter_engine import (
    build_meter_values_payload,
    start_metering_loop,
    update_evse_meter,
)

pytestmark = pytest.mark.unit


def test_build_meter_values_payload():
    """build_meter_values_payload returns OCPP-shaped dict with connectorId, transactionId, meterValue."""
    evse = EVSE(evse_id=1, max_power_W=22000.0, voltage_V=230.0)
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
    evse = EVSE(evse_id=1, max_power_W=22000.0, voltage_V=230.0)
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


def test_update_evse_meter_zero_voltage():
    """When voltage_V is 0, current_A stays 0."""
    evse = EVSE(evse_id=1, voltage_V=0.0)
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse.offered_limit_W = 11000.0
    update_evse_meter(evse, dt_s=60.0)
    assert evse.current_A == 0.0
    assert evse.power_W == 11000.0


@pytest.mark.asyncio
async def test_start_metering_loop_sends_once_then_stops():
    """start_metering_loop runs until stop_event; callback receives payload."""
    evse = EVSE(evse_id=1, voltage_V=230.0)
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
