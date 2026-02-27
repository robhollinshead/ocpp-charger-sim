"""Charger API routes."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from ocpp.v16.enums import ChargePointErrorCode
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import SessionLocal, get_db
from models.charger import Charger as ChargerModel
from repositories.charger_repository import (
    create_charger as repo_create_charger,
    delete_charger as repo_delete_charger,
    get_charger_by_charge_point_id as repo_get_charger,
    list_chargers_by_location as repo_list_chargers_by_location,
    list_evses_by_charger_id as repo_list_evses_by_charger_id,
    update_charger as repo_update_charger,
    update_charger_config as repo_update_charger_config,
)
from repositories.location_repository import get_location
from repositories.vehicle_repository import get_vehicle_by_id_tag
from schemas.chargers import (
    ChargerConfigUpdate,
    ChargerCreate,
    ChargerDetail,
    ChargerSummary,
    ChargerUpdate,
    DEFAULT_CHARGER_CONFIG,
    EvseStatus,
    FAULTED_ERROR_CODES,
    InjectStatusRequest,
    MeterSnapshot,
    OCPPLogEntry,
    StartTransactionRequest,
    StartTransactionResponse,
    StopTransactionRequest,
)
from simulator_core.charger import Charger as SimCharger
from simulator_core.evse import EVSE, EvseState
from simulator_core.ocpp_client import build_connection_url, connect_charge_point
from simulator_core.store import add as store_add, get_by_id as store_get_by_id, remove as store_remove

LOG = logging.getLogger(__name__)

router = APIRouter(tags=["chargers"])


def _resolve_vehicle_for_soc(id_tag: str) -> tuple[float, float] | None:
    """Resolve id_tag to (battery_capacity_kwh, start_soc_pct). Returns None to use 100 kWh, 20%."""
    db = SessionLocal()
    try:
        vehicle = get_vehicle_by_id_tag(db, id_tag)
        if vehicle is None:
            return None
        return (float(vehicle.battery_capacity_kwh), 20.0)
    finally:
        db.close()


def _hydrate_charger(db: Session, charge_point_id: str) -> SimCharger | None:
    """Ensure charger is in simulator store; build from DB (charger + evse rows) if missing. Returns SimCharger or None if not in DB."""
    row = repo_get_charger(db, charge_point_id)
    if row is None:
        return None
    sim = store_get_by_id(charge_point_id)
    power_type = getattr(row, "power_type", "DC") or "DC"
    if sim is not None:
        sim.power_type = power_type
        for evse in sim.evses:
            evse.power_type = power_type
        sim.set_vehicle_resolver(lambda id_tag: _resolve_vehicle_for_soc(id_tag))
        return sim
    evse_rows = repo_list_evses_by_charger_id(db, row.id)
    if not evse_rows:
        evses = [EVSE(evse_id=1, max_power_W=22000.0, power_type=power_type)]
    else:
        evses = [
            EVSE(evse_id=e.evse_id, max_power_W=22000.0, power_type=power_type)
            for e in evse_rows
        ]
    config = row.config if isinstance(row.config, dict) and row.config else dict(DEFAULT_CHARGER_CONFIG)
    sim = SimCharger(
        charge_point_id=row.charge_point_id,
        evses=evses,
        csms_url=row.connection_url,
        config=config,
        location_id=row.location_id,
        charger_name=row.charger_name,
        ocpp_version=row.ocpp_version,
        charge_point_vendor=row.charge_point_vendor or "FastCharge",
        charge_point_model=row.charge_point_model or "Pro 150",
        firmware_version=row.firmware_version or "2.4.1",
        power_type=power_type,
    )
    store_add(sim)
    sim.set_vehicle_resolver(lambda id_tag: _resolve_vehicle_for_soc(id_tag))
    return sim


_EVSE_DISPLAY_PRIORITY = (
    "Charging",
    "Preparing",
    "Finishing",
    "Faulted",
    "SuspendedEV",
    "SuspendedEVSE",
    "Unavailable",
    "Available",
)


def _representative_ocpp_status(evse_states: list[str]) -> str | None:
    """Return the highest-priority EVSE state for display (Charging > Preparing > ... > Available)."""
    if not evse_states:
        return None
    def priority(s: str) -> int:
        try:
            return _EVSE_DISPLAY_PRIORITY.index(s)
        except ValueError:
            return len(_EVSE_DISPLAY_PRIORITY)
    return min(evse_states, key=priority)


def _sim_charger_to_summary(
    c: SimCharger,
    location_id: str,
    connection_url: str,
    charger_name: str,
    ocpp_version: str,
    power_type: str = "DC",
) -> ChargerSummary:
    """Build ChargerSummary from simulator Charger and DB metadata."""
    evse_states = [evse.state.value for evse in c.evses]
    ocpp_status = _representative_ocpp_status(evse_states) if c.is_connected else None
    return ChargerSummary(
        id=c.charge_point_id,
        charge_point_id=c.charge_point_id,
        connection_url=connection_url,
        charger_name=charger_name,
        ocpp_version=ocpp_version,
        location_id=location_id,
        evse_count=len(c.evses),
        connected=c.is_connected,
        power_type=power_type if power_type in ("AC", "DC") else "DC",
        ocpp_status=ocpp_status,
    )


def _basic_auth_password_set(row: ChargerModel) -> bool:
    """True if charger has a stored Basic auth password."""
    return row.basic_auth_password is not None and len(row.basic_auth_password) > 0


def _sim_charger_to_detail(
    c: SimCharger,
    location_id: str,
    connection_url: str,
    charger_name: str,
    ocpp_version: str,
    *,
    security_profile: str = "none",
    basic_auth_password_set: bool = False,
    power_type: str = "DC",
) -> ChargerDetail:
    """Build ChargerDetail from simulator Charger and DB metadata."""
    evse_statuses = [
        EvseStatus(
            evse_id=evse.evse_id,
            state=evse.state.value,
            transaction_id=evse.transaction_id,
            id_tag=evse.id_tag,
            session_start_time=evse.session_start_time,
            meter=MeterSnapshot(
                energy_Wh=evse.energy_Wh,
                power_W=evse.power_W,
                voltage_V=evse.get_voltage_V(),
                current_A=evse.current_A,
            ),
        )
        for evse in c.evses
    ]
    return ChargerDetail(
        id=c.charge_point_id,
        charge_point_id=c.charge_point_id,
        connection_url=connection_url,
        charger_name=charger_name,
        ocpp_version=ocpp_version,
        location_id=location_id,
        charge_point_vendor=getattr(c, "charge_point_vendor", "FastCharge"),
        charge_point_model=getattr(c, "charge_point_model", "Pro 150"),
        firmware_version=getattr(c, "firmware_version", "2.4.1"),
        evses=evse_statuses,
        config=c.config,
        connected=c.is_connected,
        security_profile=security_profile if security_profile in ("none", "basic") else "none",
        basic_auth_password_set=basic_auth_password_set,
        power_type=power_type if power_type in ("AC", "DC") else "DC",
    )


@router.get("/locations/{location_id}/chargers", response_model=list[ChargerSummary])
def list_chargers_by_location(location_id: str, db: Session = Depends(get_db)) -> list[ChargerSummary]:
    """List all chargers at a location."""
    if get_location(db, location_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    db_chargers = repo_list_chargers_by_location(db, location_id)
    result = []
    for row in db_chargers:
        power_type = getattr(row, "power_type", "DC") or "DC"
        sim = store_get_by_id(row.charge_point_id)
        if sim:
            result.append(
                _sim_charger_to_summary(
                    sim, row.location_id, row.connection_url, row.charger_name, row.ocpp_version, power_type
                )
            )
        else:
            result.append(
                ChargerSummary(
                    id=row.charge_point_id,
                    charge_point_id=row.charge_point_id,
                    connection_url=row.connection_url,
                    charger_name=row.charger_name,
                    ocpp_version=row.ocpp_version,
                    location_id=row.location_id,
                    evse_count=0,
                    connected=False,
                    power_type=power_type,
                    ocpp_status=None,
                )
            )
    return result


@router.post(
    "/locations/{location_id}/chargers",
    response_model=ChargerSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_charger(
    location_id: str,
    body: ChargerCreate,
    db: Session = Depends(get_db),
) -> ChargerSummary:
    """Create a new charger at a location."""
    if get_location(db, location_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    try:
        row = repo_create_charger(
            db,
            location_id=location_id,
            charge_point_id=body.charge_point_id,
            connection_url=body.connection_url,
            charger_name=body.charger_name,
            ocpp_version=body.ocpp_version,
            evse_count=body.evse_count,
            charge_point_vendor=body.charge_point_vendor,
            charge_point_model=body.charge_point_model,
            firmware_version=body.firmware_version,
            power_type=body.power_type,
        )
    except IntegrityError as e:
        if "charge_point_id" in str(e) or "unique" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="charge_point_id already exists",
            ) from e
        raise
    power_type = row.power_type if hasattr(row, "power_type") else "DC"
    evses = [
        EVSE(evse_id=i, max_power_W=22000.0, power_type=power_type)
        for i in range(1, body.evse_count + 1)
    ]
    config = row.config if isinstance(row.config, dict) and row.config else dict(DEFAULT_CHARGER_CONFIG)
    sim = SimCharger(
        charge_point_id=row.charge_point_id,
        evses=evses,
        csms_url=row.connection_url,
        config=config,
        location_id=row.location_id,
        charger_name=row.charger_name,
        ocpp_version=row.ocpp_version,
        charge_point_vendor=row.charge_point_vendor or "FastCharge",
        charge_point_model=row.charge_point_model or "Pro 150",
        firmware_version=row.firmware_version or "2.4.1",
        power_type=power_type,
    )
    store_add(sim)
    return _sim_charger_to_summary(
        sim, row.location_id, row.connection_url, row.charger_name, row.ocpp_version, power_type
    )


@router.get("/chargers/{charge_point_id}", response_model=ChargerDetail)
def get_charger(charge_point_id: str, db: Session = Depends(get_db)) -> ChargerDetail:
    """Charger detail: EVSEs, meter values, config, connection status. Hydrates from DB if not in store."""
    sim = _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    row = repo_get_charger(db, charge_point_id)
    assert row is not None
    power_type = getattr(row, "power_type", "DC") or "DC"
    return _sim_charger_to_detail(
        sim,
        row.location_id,
        row.connection_url,
        row.charger_name,
        row.ocpp_version,
        security_profile=row.security_profile,
        basic_auth_password_set=_basic_auth_password_set(row),
        power_type=power_type,
    )


@router.post(
    "/chargers/{charge_point_id}/transactions/start",
    response_model=StartTransactionResponse,
    status_code=status.HTTP_200_OK,
)
async def start_transaction(
    charge_point_id: str,
    body: StartTransactionRequest,
    db: Session = Depends(get_db),
) -> StartTransactionResponse:
    """Start a charging transaction on an EVSE. Requires charger to be connected to CSMS."""
    sim = _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    if not sim.is_connected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charger not connected to CSMS",
        )
    client = getattr(sim, "_ocpp_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charger not connected to CSMS",
        )
    evse = sim.get_evse(body.connector_id)
    if evse is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="EVSE not found",
        )
    if evse.transaction_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="EVSE already has an active transaction",
        )
    vehicle = get_vehicle_by_id_tag(db, body.id_tag)
    battery_capacity_kwh = float(vehicle.battery_capacity_kwh) if vehicle else 100.0
    start_soc_pct = body.start_soc_pct if body.start_soc_pct is not None else 20.0
    try:
        result = await client.start_transaction(
            body.connector_id,
            body.id_tag,
            start_soc_pct=start_soc_pct,
            battery_capacity_kwh=battery_capacity_kwh,
        )
    except Exception as e:
        LOG.exception("Start transaction failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid idTag or transaction rejected by CSMS",
        )
    return StartTransactionResponse(transaction_id=result)


@router.post(
    "/chargers/{charge_point_id}/transactions/stop",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def stop_transaction(
    charge_point_id: str,
    body: StopTransactionRequest,
    db: Session = Depends(get_db),
) -> None:
    """Stop the active transaction on an EVSE."""
    sim = _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    if not sim.is_connected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charger not connected to CSMS",
        )
    client = getattr(sim, "_ocpp_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charger not connected to CSMS",
        )
    success = await client.stop_transaction(body.connector_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active transaction on that EVSE",
        )


@router.post("/chargers/{charge_point_id}/connect", status_code=status.HTTP_202_ACCEPTED)
async def connect_charger(charge_point_id: str, db: Session = Depends(get_db)) -> dict:
    """Start WebSocket connection to CSMS. Returns immediately; connection runs in background with retries."""
    sim = _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    if sim.is_connected:
        return {"status": "already_connected", "charge_point_id": charge_point_id}
    row = repo_get_charger(db, charge_point_id)
    assert row is not None
    if row.security_profile == "basic" and not _basic_auth_password_set(row):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set a password in Charger Details before connecting with Basic security",
        )
    url = build_connection_url(row.connection_url, charge_point_id)
    basic_auth_password = row.basic_auth_password if row.security_profile == "basic" else None
    sim.clear_stop_connect()
    asyncio.create_task(connect_charge_point(sim, url, basic_auth_password=basic_auth_password))
    return {"status": "connecting", "charge_point_id": charge_point_id}


@router.post("/chargers/{charge_point_id}/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_charger(charge_point_id: str, db: Session = Depends(get_db)) -> None:
    """Stop WebSocket connection and stop retrying. Idempotent."""
    sim = store_get_by_id(charge_point_id) or _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    sim.set_stop_connect(True)
    client = getattr(sim, "_ocpp_client", None)
    if client is not None:
        conn = getattr(client, "_connection", None)
        if conn is not None and getattr(conn, "open", False):
            await conn.close()
        sim.clear_ocpp_client()


@router.get("/chargers/{charge_point_id}/logs", response_model=list[OCPPLogEntry])
def get_charger_logs(charge_point_id: str, db: Session = Depends(get_db)) -> list[OCPPLogEntry]:
    """Return session-scoped OCPP message log for this charger. Empty list if not in store."""
    sim = store_get_by_id(charge_point_id) or _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    raw = sim.get_ocpp_log()
    return [OCPPLogEntry(**entry) for entry in raw]


@router.delete("/chargers/{charge_point_id}/logs", status_code=status.HTTP_204_NO_CONTENT)
def clear_charger_logs(charge_point_id: str, db: Session = Depends(get_db)) -> None:
    """Clear the session OCPP log for this charger."""
    sim = store_get_by_id(charge_point_id) or _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    sim.clear_ocpp_log()


@router.patch("/chargers/{charge_point_id}/config", response_model=ChargerDetail)
def update_charger_config(
    charge_point_id: str,
    body: ChargerConfigUpdate,
    db: Session = Depends(get_db),
) -> ChargerDetail:
    """Update charger OCPP config. Merges provided keys into stored config."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        # No changes; return current detail.
        sim = _hydrate_charger(db, charge_point_id)
        if sim is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
        row = repo_get_charger(db, charge_point_id)
        assert row is not None
        power_type = getattr(row, "power_type", "DC") or "DC"
        return _sim_charger_to_detail(
            sim,
            row.location_id,
            row.connection_url,
            row.charger_name,
            row.ocpp_version,
            security_profile=row.security_profile,
            basic_auth_password_set=_basic_auth_password_set(row),
            power_type=power_type,
        )
    row = repo_update_charger_config(db, charge_point_id, updates)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    sim = store_get_by_id(charge_point_id)
    if sim and isinstance(sim.config, dict):
        sim.config = {**sim.config, **updates}
    if sim is None:
        sim = _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    power_type = getattr(row, "power_type", "DC") or "DC"
    return _sim_charger_to_detail(
        sim,
        row.location_id,
        row.connection_url,
        row.charger_name,
        row.ocpp_version,
        security_profile=row.security_profile,
        basic_auth_password_set=_basic_auth_password_set(row),
        power_type=power_type,
    )


@router.patch("/chargers/{charge_point_id}", response_model=ChargerDetail)
def update_charger(
    charge_point_id: str,
    body: ChargerUpdate,
    db: Session = Depends(get_db),
) -> ChargerDetail:
    """Update charger attributes (identity fields not editable)."""
    row = repo_update_charger(
        db,
        charge_point_id,
        connection_url=body.connection_url,
        charger_name=body.charger_name,
        ocpp_version=body.ocpp_version,
        security_profile=body.security_profile,
        basic_auth_password=body.basic_auth_password,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    power_type = getattr(row, "power_type", "DC") or "DC"
    sim = store_get_by_id(charge_point_id)
    if sim:
        if body.connection_url is not None:
            sim.csms_url = body.connection_url
        if body.charger_name is not None:
            sim.charger_name = body.charger_name
        if body.ocpp_version is not None:
            sim.ocpp_version = body.ocpp_version
        return _sim_charger_to_detail(
            sim,
            row.location_id,
            row.connection_url,
            row.charger_name,
            row.ocpp_version,
            security_profile=row.security_profile,
            basic_auth_password_set=_basic_auth_password_set(row),
            power_type=power_type,
        )
    config = row.config if isinstance(row.config, dict) and row.config else dict(DEFAULT_CHARGER_CONFIG)
    return _sim_charger_to_detail(
        SimCharger(
            charge_point_id=row.charge_point_id,
            evses=[],
            csms_url=row.connection_url,
            config=config,
            location_id=row.location_id,
            charger_name=row.charger_name,
            ocpp_version=row.ocpp_version,
            charge_point_vendor=row.charge_point_vendor or "FastCharge",
            charge_point_model=row.charge_point_model or "Pro 150",
            firmware_version=row.firmware_version or "2.4.1",
            power_type=power_type,
        ),
        row.location_id,
        row.connection_url,
        row.charger_name,
        row.ocpp_version,
        security_profile=row.security_profile,
        basic_auth_password_set=_basic_auth_password_set(row),
        power_type=power_type,
    )


@router.delete("/chargers/{charge_point_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_charger(charge_point_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a charger by charge_point_id."""
    if not repo_delete_charger(db, charge_point_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    store_remove(charge_point_id)


@router.post("/chargers/{charge_point_id}/inject_status", status_code=status.HTTP_204_NO_CONTENT)
async def inject_status(
    charge_point_id: str,
    body: InjectStatusRequest,
    db: Session = Depends(get_db),
) -> None:
    """Inject a StatusNotification: validate the state transition, update EVSE state, and send via OCPP WebSocket."""
    sim = _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    if not sim.is_connected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charger not connected to CSMS",
        )
    client = getattr(sim, "_ocpp_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charger not connected to CSMS",
        )

    evse = sim.get_evse(body.connector_id)
    if evse is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"EVSE {body.connector_id} not found on this charger",
        )

    try:
        new_state = EvseState(body.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown status: {body.status!r}",
        )

    if not evse.can_transition_to(new_state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid transition from {evse.state.value!r} to {new_state.value!r}",
        )

    ocpp_error_code: ChargePointErrorCode | None = None
    if new_state == EvseState.Faulted:
        if not body.error_code or body.error_code not in FAULTED_ERROR_CODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="error_code is required for Faulted status and must not be 'NoError'",
            )
        ocpp_error_code = ChargePointErrorCode(body.error_code)

    evse.transition_to(new_state)
    try:
        await client.send_status_notification(
            body.connector_id,
            new_state,
            error_code=ocpp_error_code,
            info=body.info,
            vendor_error_code=body.vendor_error_code,
        )
    except Exception as e:
        LOG.exception("inject_status: send_status_notification failed for %s connector %d", charge_point_id, body.connector_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
