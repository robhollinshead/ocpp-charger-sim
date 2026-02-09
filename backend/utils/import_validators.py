"""Validate charger and vehicle rows for import."""
from typing import Any

from sqlalchemy.orm import Session

from repositories.charger_repository import get_charger_by_charge_point_id
from repositories.vehicle_repository import get_vehicle_by_id_tag, get_vehicle_by_name

# Charger import defaults (per spec)
CHARGER_DEFAULT_VENDOR = "FastCharge"
CHARGER_DEFAULT_MODEL = "Pro 150"
CHARGER_DEFAULT_FIRMWARE = "0.0.1"
CHARGER_DEFAULT_EVSE_COUNT = 1
CHARGER_DEFAULT_OCPP = "1.6"


def _get_str(row: dict[str, Any], key: str) -> str | None:
    """Get string value; empty string treated as missing."""
    v = row.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _get_positive_int(row: dict[str, Any], key: str) -> int | None:
    """Get positive integer from row; return None if missing or invalid."""
    v = row.get(key)
    if v is None:
        return None
    try:
        n = int(v) if not isinstance(v, int) else v
        return n if n >= 1 else None
    except (TypeError, ValueError):
        return None


def validate_charger_row(
    row: dict[str, Any],
    location_id: str,
    db: Session,
    default_connection_url: str | None = None,
) -> tuple[bool, dict[str, Any] | None, str]:
    """
    Validate a charger row. Returns (ok, normalized_dict, error_message).
    If ok is True, normalized_dict is ready for repo_create_charger (with evse_count, etc.).
    When connection_url is missing, default_connection_url is used if provided (non-empty).
    """
    connection_url = _get_str(row, "connection_url")
    if not connection_url and default_connection_url and str(default_connection_url).strip():
        connection_url = str(default_connection_url).strip()
    charger_name = _get_str(row, "charger_name")
    charge_point_id = _get_str(row, "charge_point_id")
    if not connection_url:
        return False, None, "connection_url is required"
    if not charger_name:
        return False, None, "charger_name is required"
    if not charge_point_id:
        return False, None, "charge_point_id is required"

    evse_count = _get_positive_int(row, "evse_count")
    if evse_count is None and row.get("evse_count") is not None:
        return False, None, "number_of_evses must be a positive integer"
    if evse_count is None:
        evse_count = CHARGER_DEFAULT_EVSE_COUNT

    if get_charger_by_charge_point_id(db, charge_point_id) is not None:
        return False, None, f"charger already exists with charge_point_id '{charge_point_id}'"

    normalized = {
        "connection_url": connection_url,
        "charger_name": charger_name,
        "charge_point_id": charge_point_id,
        "charge_point_vendor": _get_str(row, "charge_point_vendor") or CHARGER_DEFAULT_VENDOR,
        "charge_point_model": _get_str(row, "charge_point_model") or CHARGER_DEFAULT_MODEL,
        "firmware_version": _get_str(row, "firmware_version") or CHARGER_DEFAULT_FIRMWARE,
        "evse_count": evse_count,
        "ocpp_version": _get_str(row, "ocpp_version") or CHARGER_DEFAULT_OCPP,
    }
    return True, normalized, ""


def validate_vehicle_row(row: dict[str, Any], db: Session) -> tuple[bool, dict[str, Any] | None, str]:
    """
    Validate a vehicle row. Returns (ok, normalized_dict, error_message).
    normalized_dict has name, id_tag, battery_capacity_kwh (float).
    """
    name = _get_str(row, "name")
    id_tag = _get_str(row, "idTag")
    if not name:
        return False, None, "name is required"
    if not id_tag:
        return False, None, "idTag is required"

    raw_battery = row.get("battery_capacity_kWh")
    if raw_battery is None or (isinstance(raw_battery, str) and not raw_battery.strip()):
        return False, None, "battery_capacity_kWh is required"
    try:
        battery = float(raw_battery)
    except (TypeError, ValueError):
        return False, None, "battery_capacity_kWh must be numeric"
    if battery <= 0:
        return False, None, "battery_capacity_kWh must be positive"

    if get_vehicle_by_name(db, name) is not None:
        return False, None, f"vehicle with name '{name}' already exists"
    if get_vehicle_by_id_tag(db, id_tag) is not None:
        return False, None, f"vehicle with idTag '{id_tag}' already exists"

    normalized = {
        "name": name,
        "id_tag": id_tag,
        "battery_capacity_kwh": battery,
    }
    return True, normalized, ""
