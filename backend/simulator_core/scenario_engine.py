"""Scenario engine: orchestrates simulation scenarios across a location's chargers."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

from simulator_core import store
from simulator_core.evse import EvseState
from simulator_core.ocpp_client import build_connection_url, connect_charge_point

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory scenario state
# ---------------------------------------------------------------------------

@dataclass
class ScenarioRun:
    location_id: str
    scenario_type: str
    duration_minutes: int
    started_at: datetime
    total_pairs: int
    completed_pairs: int = 0
    failed_pairs: int = 0
    offline_charger_ids: list[str] = field(default_factory=list)
    status: str = "running"  # "running" | "completed" | "cancelled"


_active: dict[str, ScenarioRun] = {}


def get_active_scenario(location_id: str) -> Optional[ScenarioRun]:
    """Return the currently active scenario for a location, or None."""
    return _active.get(location_id)


def set_active_scenario(location_id: str, run: ScenarioRun) -> None:
    """Register a scenario as active for a location."""
    _active[location_id] = run


def clear_scenario(location_id: str) -> None:
    """Remove the active scenario record for a location."""
    _active.pop(location_id, None)


def clear_all() -> None:
    """Clear all active scenarios (test teardown only)."""
    _active.clear()


# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------

ConnectFn = Callable[..., Coroutine[Any, Any, None]]
SleepFn = Callable[[float], Coroutine[Any, Any, None]]

# A charger DB row duck-type: needs .charge_point_id, .connection_url,
# .security_profile, .basic_auth_password
ChargerRow = Any
# A vehicle DB row duck-type: needs .id_tags (list[str]), .battery_capacity_kwh
VehicleRow = Any


# ---------------------------------------------------------------------------
# Core scenario logic
# ---------------------------------------------------------------------------

async def _connect_if_needed(
    sim: Any,
    row: ChargerRow,
    *,
    connect_fn: ConnectFn,
    sleep_fn: SleepFn,
) -> bool:
    """
    Attempt to connect a charger if it is not already connected.
    Waits up to 5 seconds for the connection to establish.
    Returns True if connected (or was already connected), False otherwise.
    """
    if sim.is_connected:
        return True

    url = build_connection_url(row.connection_url, row.charge_point_id)
    basic_auth_password = (
        row.basic_auth_password
        if getattr(row, "security_profile", "none") == "basic"
        else None
    )
    sim.clear_stop_connect()
    asyncio.create_task(connect_fn(sim, url, basic_auth_password=basic_auth_password))
    await sleep_fn(5.0)
    return sim.is_connected


async def run_rush_period(
    location_id: str,
    duration_minutes: int,
    charger_rows: list[ChargerRow],
    vehicles: list[VehicleRow],
    *,
    connect_fn: ConnectFn = connect_charge_point,
    sleep_fn: SleepFn = asyncio.sleep,
) -> ScenarioRun:
    """
    Execute a Rush Period scenario for a location.

    Steps:
    1. Connect any disconnected chargers (wait up to 5 s each; skip failures).
    2. Collect all Available EVSEs from connected chargers.
    3. Pair Available EVSEs with vehicles (min of the two counts).
    4. Plug vehicles in one-by-one, spread evenly over *duration_minutes*.

    The first plug-in happens immediately; subsequent ones are spaced by
    ``interval = (duration_minutes * 60) / num_pairs`` seconds.
    """
    run = ScenarioRun(
        location_id=location_id,
        scenario_type="rush_period",
        duration_minutes=duration_minutes,
        started_at=datetime.now(timezone.utc),
        total_pairs=0,
    )
    set_active_scenario(location_id, run)

    # Build a lookup: charge_point_id → DB row (for URL / password)
    row_by_id: dict[str, ChargerRow] = {r.charge_point_id: r for r in charger_rows}

    # Step 1: Connect disconnected chargers
    location_sims = [s for s in store.get_all() if s.location_id == location_id]
    for sim in location_sims:
        row = row_by_id.get(sim.charge_point_id)
        if row is None:
            continue
        connected = await _connect_if_needed(sim, row, connect_fn=connect_fn, sleep_fn=sleep_fn)
        if not connected:
            LOG.warning("Scenario: charger %s failed to connect — marking offline", sim.charge_point_id)
            run.offline_charger_ids.append(sim.charge_point_id)

    # Step 2: Collect available EVSEs from connected chargers
    available_evses: list[tuple[Any, int]] = []  # (sim_charger, evse_id)
    for sim in location_sims:
        if not sim.is_connected:
            continue
        for evse in sim.evses:
            if evse.state == EvseState.Available:
                available_evses.append((sim, evse.evse_id))

    # Step 3: Build vehicle (id_tag, battery_kwh) pairs — one id_tag per vehicle
    vehicle_tags: list[tuple[str, float]] = []  # (id_tag, battery_capacity_kwh)
    for v in vehicles:
        tags = getattr(v, "id_tags", None) or getattr(v, "idTags", None) or []
        if not tags:
            continue
        # id_tags may be a list of VehicleIdTag ORM objects or plain strings
        first = tags[0]
        id_tag = first.id_tag if hasattr(first, "id_tag") else str(first)
        battery_kwh = float(getattr(v, "battery_capacity_kwh", 100.0))
        vehicle_tags.append((id_tag, battery_kwh))

    # Step 4: Pair and schedule
    num_pairs = min(len(available_evses), len(vehicle_tags))
    run.total_pairs = num_pairs

    if num_pairs == 0:
        run.status = "completed"
        return run

    interval_seconds = (duration_minutes * 60) / num_pairs
    pairs = list(zip(available_evses[:num_pairs], vehicle_tags[:num_pairs]))

    for i, ((charger_sim, evse_id), (id_tag, battery_kwh)) in enumerate(pairs):
        # Check for cancellation before each plug-in
        current = _active.get(location_id)
        if current is None or current.status == "cancelled":
            LOG.info("Scenario cancelled for location %s after %d plug-ins", location_id, i)
            break

        if i > 0:
            await sleep_fn(interval_seconds)

        # Re-check cancellation after sleep
        current = _active.get(location_id)
        if current is None or current.status == "cancelled":
            LOG.info("Scenario cancelled for location %s after %d plug-ins", location_id, i)
            break

        try:
            await charger_sim._ocpp_client.start_transaction(
                evse_id,
                id_tag,
                start_soc_pct=20.0,
                battery_capacity_kwh=battery_kwh,
            )
            run.completed_pairs += 1
            LOG.info(
                "Scenario: plugged in %s on %s EVSE %d",
                id_tag,
                charger_sim.charge_point_id,
                evse_id,
            )
        except Exception as exc:
            LOG.error(
                "Scenario: failed to start transaction %s on %s EVSE %d: %s",
                id_tag,
                charger_sim.charge_point_id,
                evse_id,
                exc,
            )
            run.failed_pairs += 1

    if run.status == "running":
        run.status = "completed"

    return run
