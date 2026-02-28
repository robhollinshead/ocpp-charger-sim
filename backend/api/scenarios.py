"""Scenario API routes — location-scoped scenario management."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from repositories.charger_repository import list_chargers_by_location as repo_list_chargers
from repositories.location_repository import get_location
from repositories.vehicle_repository import list_vehicles_by_location as repo_list_vehicles
from schemas.scenarios import RushPeriodConfig, ScenarioRunResponse, StopAllChargingResponse
from simulator_core import store
from simulator_core.scenario_engine import (
    clear_scenario,
    get_active_scenario,
    run_rush_period,
    set_active_scenario,
    ScenarioRun,
)

from datetime import datetime, timezone

LOG = logging.getLogger(__name__)

router = APIRouter(tags=["scenarios"])


def _run_to_response(run: ScenarioRun) -> ScenarioRunResponse:
    return ScenarioRunResponse(
        location_id=run.location_id,
        scenario_type=run.scenario_type,
        duration_minutes=run.duration_minutes,
        started_at=run.started_at.isoformat().replace("+00:00", "Z"),
        total_pairs=run.total_pairs,
        completed_pairs=run.completed_pairs,
        failed_pairs=run.failed_pairs,
        offline_charger_ids=run.offline_charger_ids,
        status=run.status,
    )


@router.post(
    "/locations/{location_id}/scenarios/rush-period",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ScenarioRunResponse,
)
async def start_rush_period(
    location_id: str,
    config: RushPeriodConfig,
    db: Session = Depends(get_db),
) -> ScenarioRunResponse:
    """Start a Rush Period scenario for a location. Returns 409 if one is already running."""
    if get_location(db, location_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

    existing = get_active_scenario(location_id)
    if existing is not None and existing.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A scenario is already running for this location",
        )

    charger_rows = repo_list_chargers(db, location_id)
    vehicles = repo_list_vehicles(db, location_id)

    # Create a placeholder run so callers can poll immediately
    placeholder = ScenarioRun(
        location_id=location_id,
        scenario_type="rush_period",
        duration_minutes=config.duration_minutes,
        started_at=datetime.now(timezone.utc),
        total_pairs=0,
        status="running",
    )
    set_active_scenario(location_id, placeholder)

    asyncio.create_task(
        run_rush_period(
            location_id,
            config.duration_minutes,
            charger_rows,
            vehicles,
        )
    )

    return _run_to_response(placeholder)


@router.get(
    "/locations/{location_id}/scenarios/active",
    response_model=ScenarioRunResponse | None,
)
def get_active(location_id: str) -> ScenarioRunResponse | None:
    """Return the currently active scenario for a location, or null."""
    run = get_active_scenario(location_id)
    if run is None:
        return None
    return _run_to_response(run)


@router.delete(
    "/locations/{location_id}/scenarios/active",
    status_code=status.HTTP_204_NO_CONTENT,
)
def cancel_scenario(location_id: str) -> None:
    """Cancel the active scenario for a location (halts further plug-ins)."""
    run = get_active_scenario(location_id)
    if run is not None:
        run.status = "cancelled"
        clear_scenario(location_id)


@router.post(
    "/locations/{location_id}/scenarios/stop-all-charging",
    response_model=StopAllChargingResponse,
)
async def stop_all_charging(location_id: str) -> StopAllChargingResponse:
    """
    Send StopTransaction to every active EVSE across all connected chargers at this location.
    Returns counts of stopped and failed transactions.
    """
    location_sims = [s for s in store.get_all() if s.location_id == location_id]
    stopped = 0
    errors = 0

    for sim in location_sims:
        if not sim.is_connected:
            continue
        for evse in sim.evses:
            if evse.transaction_id is None:
                continue
            try:
                await sim._ocpp_client.stop_transaction(evse.evse_id)
                stopped += 1
            except Exception as exc:
                LOG.error(
                    "stop-all-charging: failed to stop EVSE %d on %s: %s",
                    evse.evse_id,
                    sim.charge_point_id,
                    exc,
                )
                errors += 1

    return StopAllChargingResponse(stopped=stopped, errors=errors)
