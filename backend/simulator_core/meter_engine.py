"""Per-EVSE MeterValues engine: asyncio loop, update rules, OCPP payload (ocpp-meter-values.md)."""
import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Awaitable, Callable

from simulator_core.evse import EVSE, EvseState

if TYPE_CHECKING:
    pass

# OCPP 1.6 MeterValues payload shape for the callback (connectorId, transactionId, meterValue)
MeterValuesPayload = dict


def build_meter_values_payload(evse: EVSE) -> MeterValuesPayload:
    """Build OCPP 1.6 MeterValues request payload (FR-4)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return {
        "connectorId": evse.evse_id,
        "transactionId": evse.transaction_id,
        "meterValue": [
            {
                "timestamp": now,
                "sampledValue": [
                    {"value": str(int(round(evse.energy_Wh))), "measurand": "Energy.Active.Import.Register", "unit": "Wh"},
                    {"value": str(int(round(evse.power_W))), "measurand": "Power.Active.Import", "unit": "W"},
                    {"value": f"{evse.current_A:.1f}", "measurand": "Current.Import", "unit": "A"},
                    {"value": str(round(evse.soc_pct, 1)), "measurand": "SoC", "unit": "Percent", "location": "EV"},
                ],
            }
        ],
    }


def update_evse_meter(evse: EVSE, dt_s: float) -> None:
    """
    Update EVSE internal meter state for elapsed time (FR-3).
    energy_Wh += power * dt; power = min(offered_limit, max_power); current = power / voltage.
    SoC = start_soc_pct + (session_energy_Wh / battery_capacity_Wh) * 100, capped at 100.
    """
    power_W = evse.get_effective_power_W()
    evse.power_W = power_W
    evse.energy_Wh += power_W * (dt_s / 3600.0)
    evse.current_A = power_W / evse.voltage_V if evse.voltage_V else 0.0
    session_energy_Wh = evse.energy_Wh - evse._initial_energy_Wh
    evse.soc_pct = min(
        100.0,
        evse.start_soc_pct + (session_energy_Wh / evse.battery_capacity_Wh) * 100.0,
    )


SendMeterValuesCb = Callable[[MeterValuesPayload], Awaitable[None]]


async def _metering_loop(
    evse: EVSE,
    send_cb: SendMeterValuesCb,
    interval_s: float,
    stop_event: asyncio.Event,
) -> None:
    """
    Single EVSE metering loop. Runs only while Charging and transaction active.
    Stops when stop_event is set or state is no longer Charging.
    """
    while not stop_event.is_set() and evse.state == EvseState.Charging and evse.transaction_id is not None:
        update_evse_meter(evse, interval_s)
        payload = build_meter_values_payload(evse)
        await send_cb(payload)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            continue


def start_metering_loop(
    evse: EVSE,
    send_cb: SendMeterValuesCb,
    interval_s: float = 10.0,
) -> tuple[asyncio.Task, asyncio.Event]:
    """
    Start one asyncio task per EVSE (FR-1). Callback receives OCPP-shaped payload.
    Returns (task, stop_event). Cancel by setting stop_event or cancelling the task.
    """
    stop_event = asyncio.Event()
    task = asyncio.create_task(_metering_loop(evse, send_cb, interval_s, stop_event))
    return task, stop_event
