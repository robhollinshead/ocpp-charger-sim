"""Per-EVSE MeterValues engine: asyncio loop, update rules, OCPP payload (ocpp-meter-values.md)."""
import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Awaitable, Callable

from simulator_core.evse import EVSE, EvseState

if TYPE_CHECKING:
    pass

# OCPP 1.6 MeterValues payload shape for the callback (connectorId, transactionId, meterValue)
MeterValuesPayload = dict


def build_meter_values_payload(evse: EVSE, power_type: str = "DC") -> MeterValuesPayload:
    """Build OCPP 1.6 MeterValues request payload (FR-4).

    For AC chargers, SoC is excluded from the payload (not reported by real AC chargers).
    SoC is still calculated internally for session end detection.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    sampled_values = [
        {"value": str(int(round(evse.energy_Wh))), "measurand": "Energy.Active.Import.Register", "unit": "Wh"},
        {"value": str(int(round(evse.power_W))), "measurand": "Power.Active.Import", "unit": "W"},
        {"value": f"{evse.current_A:.1f}", "measurand": "Current.Import", "unit": "A"},
    ]
    # Only include SoC for DC chargers (AC chargers don't report battery SoC)
    if power_type == "DC":
        sampled_values.append(
            {"value": str(round(evse.soc_pct, 1)), "measurand": "SoC", "unit": "Percent", "location": "EV"}
        )
    return {
        "connectorId": evse.evse_id,
        "transactionId": evse.transaction_id,
        "meterValue": [
            {
                "timestamp": now,
                "sampledValue": sampled_values,
            }
        ],
    }


def update_evse_meter(evse: EVSE, dt_s: float) -> None:
    """
    Update EVSE internal meter state for elapsed time (FR-3).

    For DC chargers:
        Power from offered_limit_W; current = power / voltage (OCV model).

    For AC chargers:
        Power from offered_limit_W; current = power / (sqrt(3) * 400V).
        The offered_limit_W is already in Watts (converted from Amps by SetChargingProfile handler).

    SoC is always calculated for session end detection, regardless of power type.
    """
    power_W = evse.get_effective_power_W()
    evse.power_W = power_W
    evse.energy_Wh += power_W * (dt_s / 3600.0)
    session_energy_Wh = evse.energy_Wh - evse._initial_energy_Wh
    evse.soc_pct = min(
        100.0,
        evse.start_soc_pct + (session_energy_Wh / evse.battery_capacity_Wh) * 100.0,
    )
    if evse.power_type == "AC":
        # AC: derive current from power using 3-phase formula
        evse.current_A = evse.ac_power_to_current_A(power_W)
    else:
        # DC: derive current from power / voltage
        voltage = evse.get_voltage_V()
        evse.current_A = power_W / voltage if voltage else 0.0


SendMeterValuesCb = Callable[[MeterValuesPayload], Awaitable[None]]


async def _metering_loop(
    evse: EVSE,
    send_cb: SendMeterValuesCb,
    interval_s: float,
    stop_event: asyncio.Event,
    power_type: str = "DC",
) -> None:
    """
    Single EVSE metering loop. Runs only while Charging and transaction active.
    Stops when stop_event is set or state is no longer Charging.
    """
    while not stop_event.is_set() and evse.state == EvseState.Charging and evse.transaction_id is not None:
        update_evse_meter(evse, interval_s)
        payload = build_meter_values_payload(evse, power_type)
        await send_cb(payload)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            continue


def start_metering_loop(
    evse: EVSE,
    send_cb: SendMeterValuesCb,
    interval_s: float = 10.0,
    power_type: str = "DC",
) -> tuple[asyncio.Task, asyncio.Event]:
    """
    Start one asyncio task per EVSE (FR-1). Callback receives OCPP-shaped payload.
    Returns (task, stop_event). Cancel by setting stop_event or cancelling the task.
    """
    stop_event = asyncio.Event()
    task = asyncio.create_task(_metering_loop(evse, send_cb, interval_s, stop_event, power_type))
    return task, stop_event
