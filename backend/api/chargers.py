"""Charger API routes."""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status

LOG = logging.getLogger(__name__)
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
    MeterSnapshot,
    OCPPLogEntry,
    StartTransactionRequest,
    StartTransactionResponse,
    StopTransactionRequest,
)
from simulator_core.charger import Charger as SimCharger
from simulator_core.evse import EVSE
from simulator_core.ocpp_client import build_connection_url, connect_charge_point
from simulator_core.store import add as store_add, get_by_id as store_get_by_id, remove as store_remove

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
    if sim is not None:
        sim.set_vehicle_resolver(lambda id_tag: _resolve_vehicle_for_soc(id_tag))
        return sim
    evse_rows = repo_list_evses_by_charger_id(db, row.id)
    if not evse_rows:
        evses = [EVSE(evse_id=1, max_power_W=22000.0, voltage_V=230.0)]
    else:
        evses = [
            EVSE(evse_id=e.evse_id, max_power_W=22000.0, voltage_V=230.0)
            for e in evse_rows
        ]
    config = row.config if isinstance(row.config, dict) and row.config else dict(DEFAULT_CHARGER_CONFIG)
    if "voltage_V" not in config:
        config = {**config, "voltage_V": 230.0}
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
    )
    store_add(sim)
    sim.set_vehicle_resolver(lambda id_tag: _resolve_vehicle_for_soc(id_tag))
    return sim


def _sim_charger_to_summary(c: SimCharger, location_id: str, connection_url: str, charger_name: str, ocpp_version: str) -> ChargerSummary:
    """Build ChargerSummary from simulator Charger and DB metadata."""
    return ChargerSummary(
        id=c.charge_point_id,
        charge_point_id=c.charge_point_id,
        connection_url=connection_url,
        charger_name=charger_name,
        ocpp_version=ocpp_version,
        location_id=location_id,
        evse_count=len(c.evses),
        connected=c.is_connected,
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
                voltage_V=evse.voltage_V,
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
    )


@router.get("/locations/{location_id}/chargers", response_model=list[ChargerSummary])
def list_chargers_by_location(location_id: str, db: Session = Depends(get_db)) -> list[ChargerSummary]:
    """List all chargers at a location."""
    if get_location(db, location_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    db_chargers = repo_list_chargers_by_location(db, location_id)
    result = []
    for row in db_chargers:
        sim = store_get_by_id(row.charge_point_id)
        if sim:
            result.append(
                _sim_charger_to_summary(
                    sim, row.location_id, row.connection_url, row.charger_name, row.ocpp_version
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
        )
    except IntegrityError as e:
        if "charge_point_id" in str(e) or "unique" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="charge_point_id already exists",
            ) from e
        raise
    evses = [
        EVSE(evse_id=i, max_power_W=22000.0, voltage_V=230.0)
        for i in range(1, body.evse_count + 1)
    ]
    config = row.config if isinstance(row.config, dict) and row.config else dict(DEFAULT_CHARGER_CONFIG)
    config.setdefault("voltage_V", 230.0)
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
    )
    store_add(sim)
    return _sim_charger_to_summary(
        sim, row.location_id, row.connection_url, row.charger_name, row.ocpp_version
    )


@router.get("/chargers/{charge_point_id}", response_model=ChargerDetail)
def get_charger(charge_point_id: str, db: Session = Depends(get_db)) -> ChargerDetail:
    """Charger detail: EVSEs, meter values, config, connection status. Hydrates from DB if not in store."""
    sim = _hydrate_charger(db, charge_point_id)
    if sim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    row = repo_get_charger(db, charge_point_id)
    assert row is not None
    return _sim_charger_to_detail(
        sim,
        row.location_id,
        row.connection_url,
        row.charger_name,
        row.ocpp_version,
        security_profile=row.security_profile,
        basic_auth_password_set=_basic_auth_password_set(row),
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
        return _sim_charger_to_detail(
            sim,
            row.location_id,
            row.connection_url,
            row.charger_name,
            row.ocpp_version,
            security_profile=row.security_profile,
            basic_auth_password_set=_basic_auth_password_set(row),
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
    return _sim_charger_to_detail(
        sim,
        row.location_id,
        row.connection_url,
        row.charger_name,
        row.ocpp_version,
        security_profile=row.security_profile,
        basic_auth_password_set=_basic_auth_password_set(row),
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
        ),
        row.location_id,
        row.connection_url,
        row.charger_name,
        row.ocpp_version,
        security_profile=row.security_profile,
        basic_auth_password_set=_basic_auth_password_set(row),
    )


@router.delete("/chargers/{charge_point_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_charger(charge_point_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a charger by charge_point_id."""
    if not repo_delete_charger(db, charge_point_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Charger not found")
    store_remove(charge_point_id)
