"""Charging Profile inspection API endpoints."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db
from schemas.charging_profiles import ChargingProfileResponse, ChargingSchedulePeriodResponse, EvaluatedLimitResponse
from simulator_core.charging_profile import ChargingProfile, evaluate_profiles

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hydrate_charger(db: Session, charge_point_id: str):
    """Minimal hydration: look up charger in simulator store (or 404)."""
    from api.chargers import _hydrate_charger as _base_hydrate
    return _base_hydrate(db, charge_point_id)


def _profile_status(p: ChargingProfile, now: datetime) -> str:
    if p.valid_to is not None and now >= p.valid_to:
        return "Expired"
    if p.valid_from is not None and now < p.valid_from:
        return "Scheduled"
    return "Active"


def _dt_str(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _profile_to_response(
    p: ChargingProfile,
    now: datetime,
    current_limit_W: Optional[float],
    status: str,
) -> ChargingProfileResponse:
    periods = [
        ChargingSchedulePeriodResponse(
            start_period_s=sp.start_period_s,
            limit_W=sp.limit_W,
            raw_limit=sp.raw_limit,
            raw_unit=sp.raw_unit,
            number_phases=sp.number_phases,
        )
        for sp in p.charging_schedule_periods
    ]
    return ChargingProfileResponse(
        charging_profile_id=p.charging_profile_id,
        connector_id=p.connector_id,
        stack_level=p.stack_level,
        charging_profile_purpose=p.charging_profile_purpose,
        charging_profile_kind=p.charging_profile_kind,
        recurrency_kind=p.recurrency_kind,
        transaction_id=p.transaction_id,
        valid_from=_dt_str(p.valid_from),
        valid_to=_dt_str(p.valid_to),
        start_schedule=_dt_str(p.start_schedule),
        duration_s=p.duration_s,
        charging_schedule_periods=periods,
        received_at=p.received_at.isoformat().replace("+00:00", "Z"),
        status=status,
        current_limit_W=current_limit_W if status == "Active" else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/chargers/{charge_point_id}/charging-profiles",
    response_model=list[ChargingProfileResponse],
)
def list_charging_profiles(
    charge_point_id: str,
    db: Session = Depends(get_db),
) -> list[ChargingProfileResponse]:
    """List all charging profiles stored for the charger."""
    sim = _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=404, detail="Charger not found")

    now = datetime.now(timezone.utc)
    result = []
    for p in sim._charging_profiles:
        status = _profile_status(p, now)
        # Evaluate current limit only for active profiles
        current_limit_W: Optional[float] = None
        if status == "Active":
            evse = sim.get_evse(p.connector_id) if p.connector_id != 0 else None
            tx_id = evse.transaction_id if evse else None
            tx_start = None
            if evse and evse.session_start_time:
                try:
                    tx_start = datetime.fromisoformat(
                        evse.session_start_time.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
            eval_result = evaluate_profiles(
                [p], now, p.connector_id, tx_id, tx_start
            )
            current_limit_W = eval_result.limit_W if eval_result else None
        result.append(_profile_to_response(p, now, current_limit_W, status))
    return result


@router.get(
    "/chargers/{charge_point_id}/charging-profiles/evaluate",
    response_model=EvaluatedLimitResponse,
)
def evaluate_charging_profile(
    charge_point_id: str,
    connector_id: int = 1,
    transaction_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> EvaluatedLimitResponse:
    """Evaluate the current effective charging limit for a connector."""
    sim = _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=404, detail="Charger not found")

    now = datetime.now(timezone.utc)
    evse = sim.get_evse(connector_id)
    tx_id = transaction_id or (evse.transaction_id if evse else None)
    tx_start = None
    if evse and evse.session_start_time:
        try:
            tx_start = datetime.fromisoformat(
                evse.session_start_time.replace("Z", "+00:00")
            )
        except ValueError:
            pass

    result = evaluate_profiles(sim._charging_profiles, now, connector_id, tx_id, tx_start)
    limit_W = result.limit_W if result else None
    return EvaluatedLimitResponse(
        connector_id=connector_id,
        transaction_id=tx_id,
        limit_W=limit_W,
        effective_W=limit_W if limit_W is not None else 0.0,
        profile_id=result.profile_id if result else None,
        purpose=result.purpose if result else None,
        stack_level=result.stack_level if result else None,
        capped_by_max_profile=result.capped_by_max_profile if result else False,
    )
