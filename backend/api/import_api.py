"""Import API: file upload for chargers/vehicles and template downloads."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import get_db
from repositories.charger_repository import create_charger as repo_create_charger
from repositories.location_repository import get_location
from repositories.vehicle_repository import create_vehicle as repo_create_vehicle
from schemas.chargers import ChargerSummary, DEFAULT_CHARGER_CONFIG
from schemas.vehicles import VehicleResponse
from simulator_core.charger import Charger as SimCharger
from simulator_core.evse import EVSE
from simulator_core.store import add as store_add
from utils.import_parsers import parse_upload
from utils.import_validators import validate_charger_row, validate_vehicle_row

router = APIRouter(tags=["import"])

# --- Template content (spec) ---
CHARGERS_CSV_TEMPLATE = "connection_url,charger_name,charge_point_id,charge_point_vendor,charge_point_model,firmware_version,number_of_evses,ocpp_version\n\n"
CHARGERS_JSON_TEMPLATE = """[
  {
    "connection_url": "ws://example.com/ocpp/A01",
    "charger_name": "Charger 01",
    "charge_point_id": "A01",
    "charge_point_vendor": "FastCharge",
    "charge_point_model": "Pro 150",
    "firmware_version": "0.0.1",
    "number_of_evses": 1,
    "ocpp_version": "1.6"
  }
]
"""
VEHICLES_CSV_TEMPLATE = 'name,idTag,battery_capacity_kWh\nVehicle 1,ABC12345,75\n"Vehicle 2","60603912110f,6060391212ee",75\n\n'
VEHICLES_JSON_TEMPLATE = """[
  {
    "name": "Test Vehicle",
    "idTag": "ABC12345",
    "battery_capacity_kWh": 75
  },
  {
    "name": "Vehicle 2",
    "idTag": "60603912110f,6060391212ee",
    "battery_capacity_kWh": 75
  }
]
"""


async def _read_upload(file: UploadFile) -> bytes:
    """Read full content of uploaded file."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    return content


@router.post("/locations/{location_id}/import/chargers")
async def import_chargers(
    location_id: str,
    file: UploadFile = File(...),
    default_connection_url: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    """Upload CSV or JSON; import valid charger rows; return success and failed lists.
    If default_connection_url is provided, it is used for any row missing connection_url."""
    if get_location(db, location_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    try:
        content = await _read_upload(file)
        rows = parse_upload(content, file.filename, charger_format=True)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    default_url = default_connection_url.strip() if default_connection_url and isinstance(default_connection_url, str) else None

    success: list[dict] = []
    failed: list[dict] = []

    for raw_row in rows:
        ok, normalized, err = validate_charger_row(raw_row, location_id, db, default_connection_url=default_url)
        if not ok or normalized is None:
            failed.append({"row": raw_row, "error": err})
            continue
        try:
            row = repo_create_charger(
                db,
                location_id=location_id,
                charge_point_id=normalized["charge_point_id"],
                connection_url=normalized["connection_url"],
                charger_name=normalized["charger_name"],
                ocpp_version=normalized["ocpp_version"],
                evse_count=normalized["evse_count"],
                charge_point_vendor=normalized["charge_point_vendor"],
                charge_point_model=normalized["charge_point_model"],
                firmware_version=normalized["firmware_version"],
            )
        except IntegrityError:
            failed.append({"row": raw_row, "error": f"charger already exists with charge_point_id '{normalized['charge_point_id']}'"})
            continue
        evses = [
            EVSE(evse_id=i, max_power_W=22000.0, voltage_V=230.0)
            for i in range(1, normalized["evse_count"] + 1)
        ]
        config = dict(DEFAULT_CHARGER_CONFIG)
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
            firmware_version=row.firmware_version or "0.0.1",
        )
        store_add(sim)
        success.append(
            ChargerSummary(
                id=row.charge_point_id,
                charge_point_id=row.charge_point_id,
                connection_url=row.connection_url,
                charger_name=row.charger_name,
                ocpp_version=row.ocpp_version,
                location_id=row.location_id,
                evse_count=len(evses),
                connected=False,
            ).model_dump()
        )

    return {"success": success, "failed": failed}


@router.post("/locations/{location_id}/import/vehicles")
async def import_vehicles(
    location_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload CSV or JSON; import valid vehicle rows; return success and failed lists."""
    if get_location(db, location_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    try:
        content = await _read_upload(file)
        rows = parse_upload(content, file.filename, charger_format=False)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    success: list[dict] = []
    failed: list[dict] = []

    for raw_row in rows:
        ok, normalized, err = validate_vehicle_row(raw_row, db)
        if not ok or normalized is None:
            failed.append({"row": raw_row, "error": err})
            continue
        try:
            vehicle = repo_create_vehicle(
                db,
                location_id=location_id,
                name=normalized["name"],
                id_tags=normalized["id_tags"],
                battery_capacity_kwh=normalized["battery_capacity_kwh"],
            )
        except IntegrityError:
            failed.append({"row": raw_row, "error": "vehicle with that name or idTag already exists"})
            continue
        id_tags = [t.id_tag for t in vehicle.id_tags] if vehicle.id_tags else normalized["id_tags"]
        success.append(
            VehicleResponse(
                id=vehicle.id,
                name=vehicle.name,
                idTags=id_tags,
                battery_capacity_kWh=float(vehicle.battery_capacity_kwh),
                location_id=vehicle.location_id,
            ).model_dump()
        )

    return {"success": success, "failed": failed}


@router.get("/import/templates/chargers.csv", response_class=Response)
def template_chargers_csv():
    """Download chargers CSV template."""
    return Response(
        content=CHARGERS_CSV_TEMPLATE,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="chargers.csv"'},
    )


@router.get("/import/templates/chargers.json", response_class=Response)
def template_chargers_json():
    """Download chargers JSON template."""
    return Response(
        content=CHARGERS_JSON_TEMPLATE,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="chargers.json"'},
    )


@router.get("/import/templates/vehicles.csv", response_class=Response)
def template_vehicles_csv():
    """Download vehicles CSV template."""
    return Response(
        content=VEHICLES_CSV_TEMPLATE,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="vehicles.csv"'},
    )


@router.get("/import/templates/vehicles.json", response_class=Response)
def template_vehicles_json():
    """Download vehicles JSON template."""
    return Response(
        content=VEHICLES_JSON_TEMPLATE,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="vehicles.json"'},
    )
