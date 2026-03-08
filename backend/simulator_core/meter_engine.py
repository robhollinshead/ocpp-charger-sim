"""Per-EVSE MeterValues engine: asyncio loop, update rules, OCPP payload (ocpp-meter-values.md)."""
import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Awaitable, Callable

from simulator_core.evse import EVSE, EvseState

if TYPE_CHECKING:
    pass

# OCPP 1.6 MeterValues payload shape for the callback (connectorId, transactionId, meterValue)
MeterValuesPayload = dict

# Phase-level AC measurand token → (wire measurand, phase, unit).
# Voltage and current for all phases are simplified: same value as the aggregate.
_PHASE_MEASURAND_MAP: dict[str, tuple[str, str, str]] = {
    "Current.Import.L1": ("Current.Import", "L1", "A"),
    "Current.Import.L2": ("Current.Import", "L2", "A"),
    "Current.Import.L3": ("Current.Import", "L3", "A"),
    "Voltage.L1-N":      ("Voltage", "L1-N", "V"),
    "Voltage.L2-N":      ("Voltage", "L2-N", "V"),
    "Voltage.L3-N":      ("Voltage", "L3-N", "V"),
}

# Fixed line-to-neutral voltage for AC phase measurands (V).
_AC_PHASE_VOLTAGE_V = 230


def _build_sampled_value(token: str, evse: EVSE) -> dict | None:
    """Return a single OCPP sampledValue dict for the given measurand token, or None if unknown."""
    if token == "Energy.Active.Import.Register":
        return {"value": str(int(round(evse.energy_Wh))), "measurand": token, "unit": "Wh"}
    if token == "Power.Active.Import":
        return {"value": str(int(round(evse.power_W))), "measurand": token, "unit": "W"}
    if token == "Current.Import":
        return {"value": f"{evse.current_A:.1f}", "measurand": token, "unit": "A"}
    if token == "SoC":
        return {"value": str(round(evse.soc_pct, 1)), "measurand": token, "unit": "Percent", "location": "EV"}
    if token in _PHASE_MEASURAND_MAP:
        wire_measurand, phase, unit = _PHASE_MEASURAND_MAP[token]
        if unit == "A":
            value = f"{evse.current_A:.1f}"
        else:
            value = str(_AC_PHASE_VOLTAGE_V)
        return {"value": value, "measurand": wire_measurand, "phase": phase, "unit": unit}
    return None


def build_meter_values_payload(evse: EVSE, measurands: list[str]) -> MeterValuesPayload:
    """Build OCPP 1.6 MeterValues request payload for the configured measurands (FR-4).

    Only measurands listed in `measurands` are included in the payload.
    SoC is still calculated internally for session end detection regardless of configuration.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    sampled_values = [sv for token in measurands if (sv := _build_sampled_value(token, evse)) is not None]
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
OnSocFullCb = Callable[[], Awaitable[None]]


async def _metering_loop(
    evse: EVSE,
    send_cb: SendMeterValuesCb,
    interval_s: float,
    stop_event: asyncio.Event,
    measurands: list[str],
    on_soc_full: OnSocFullCb | None = None,
) -> None:
    """
    Single EVSE metering loop. Runs while Charging or SuspendedEV and transaction active.
    Stops when stop_event is set or state is neither Charging nor SuspendedEV.
    When SoC reaches 100% and state is Charging, calls on_soc_full once (transition to SuspendedEV);
    loop continues with 0 effective power.
    """
    while (
        not stop_event.is_set()
        and evse.state in (EvseState.Charging, EvseState.SuspendedEV)
        and evse.transaction_id is not None
    ):
        update_evse_meter(evse, interval_s)
        payload = build_meter_values_payload(evse, measurands)
        await send_cb(payload)
        if (
            evse.soc_pct >= 100.0
            and evse.state == EvseState.Charging
            and on_soc_full is not None
        ):
            await on_soc_full()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            continue


def start_metering_loop(
    evse: EVSE,
    send_cb: SendMeterValuesCb,
    measurands: list[str],
    interval_s: float = 10.0,
    on_soc_full: OnSocFullCb | None = None,
) -> tuple[asyncio.Task, asyncio.Event]:
    """
    Start one asyncio task per EVSE (FR-1). Callback receives OCPP-shaped payload.
    Returns (task, stop_event). Cancel by setting stop_event or cancelling the task.
    Optional on_soc_full is called once when SoC reaches 100% while Charging (e.g. to transition to SuspendedEV).
    measurands: list of MeterValuesSampledData tokens to include in each MeterValues message.
    """
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        _metering_loop(evse, send_cb, interval_s, stop_event, measurands, on_soc_full)
    )
    return task, stop_event
