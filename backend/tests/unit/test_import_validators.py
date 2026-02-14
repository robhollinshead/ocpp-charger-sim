"""Unit tests: import validators (charger and vehicle row validation)."""
import pytest

from repositories.location_repository import create_location
from repositories.vehicle_repository import create_vehicle
from utils.import_validators import validate_charger_row, validate_vehicle_row

pytestmark = pytest.mark.unit


@pytest.fixture
def loc_id(db_session):
    """Create a location for validator tests (unique per test)."""
    import uuid
    lid = f"loc-valid-{uuid.uuid4().hex[:8]}"
    loc = create_location(db_session, "Validator Loc", "1 St", lid)
    return loc.id


def test_validate_charger_row_success(db_session, loc_id):
    """validate_charger_row with valid row returns (True, normalized, '')."""
    row = {"connection_url": "ws://x/ocpp", "charger_name": "Charger", "charge_point_id": "CP-VALID"}
    ok, norm, err = validate_charger_row(row, loc_id, db_session)
    assert ok is True and norm is not None and norm["charge_point_id"] == "CP-VALID" and err == ""


def test_validate_charger_row_missing_connection_url(db_session, loc_id):
    """validate_charger_row without connection_url returns error."""
    row = {"charger_name": "C", "charge_point_id": "CP"}
    ok, norm, err = validate_charger_row(row, loc_id, db_session)
    assert ok is False and "connection_url" in err


def test_validate_charger_row_default_connection_url(db_session, loc_id):
    """validate_charger_row uses default_connection_url when connection_url missing."""
    row = {"charger_name": "C", "charge_point_id": "CP-DEF"}
    ok, norm, _ = validate_charger_row(row, loc_id, db_session, default_connection_url="ws://default/ocpp")
    assert ok is True and norm["connection_url"] == "ws://default/ocpp"


def test_validate_vehicle_row_success(db_session, loc_id):
    """validate_vehicle_row with valid row returns (True, normalized, '')."""
    row = {"name": "Vehicle One", "idTag": "TAG-V1", "battery_capacity_kWh": 75}
    ok, norm, err = validate_vehicle_row(row, db_session)
    assert ok is True and norm["name"] == "Vehicle One" and norm["id_tags"] == ["TAG-V1"] and err == ""


def test_validate_vehicle_row_missing_name(db_session):
    """validate_vehicle_row without name returns error."""
    ok, _, err = validate_vehicle_row({"idTag": "T1", "battery_capacity_kWh": 50}, db_session)
    assert ok is False and "name" in err


def test_validate_vehicle_row_invalid_battery(db_session):
    """validate_vehicle_row with non-numeric battery returns error."""
    ok, _, err = validate_vehicle_row({"name": "V", "idTag": "T1", "battery_capacity_kWh": "x"}, db_session)
    assert ok is False


def test_validate_charger_row_evse_count_invalid(db_session, loc_id):
    """validate_charger_row with invalid evse_count returns error."""
    row = {"connection_url": "ws://x", "charger_name": "C", "charge_point_id": "CP-X", "evse_count": "x"}
    ok, norm, err = validate_charger_row(row, loc_id, db_session)
    assert ok is False and "integer" in err


def test_validate_vehicle_row_duplicate_id_tag(db_session, loc_id):
    """validate_vehicle_row returns error when idTag already exists."""
    create_vehicle(db_session, location_id=loc_id, name="Other", id_tags=["TAG-TAKEN"], battery_capacity_kwh=70.0)
    row = {"name": "New V", "idTag": "TAG-TAKEN", "battery_capacity_kWh": 50}
    ok, _, err = validate_vehicle_row(row, db_session)
    assert ok is False and "idTag" in err
