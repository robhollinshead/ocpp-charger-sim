"""API route handlers."""
from fastapi import APIRouter

from schemas.chargers import ChargerSummary
from schemas.health import HealthResponse
from simulator_core.store import get_all

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@router.get("/chargers", response_model=list[ChargerSummary])
def list_chargers() -> list[ChargerSummary]:
    """List all chargers in the active store."""
    chargers = get_all()
    return [
        ChargerSummary(
            id=c.charge_point_id,
            charge_point_id=c.charge_point_id,
            connection_url=c.csms_url or "",
            charger_name=c.charger_name or c.charge_point_id,
            ocpp_version=c.ocpp_version,
            location_id=c.location_id or "",
            evse_count=len(c.evses),
            connected=c.is_connected,
        )
        for c in chargers
    ]
