"""Integration tests: charger repository with test DB session."""
import uuid

import pytest

from repositories.charger_repository import (
    count_chargers_by_location,
    create_charger,
    delete_charger,
    get_charger_by_charge_point_id,
    list_chargers_by_location,
    list_all_chargers,
    list_evses_by_charger_id,
    update_charger,
    update_charger_config,
)
from repositories.location_repository import create_location

pytestmark = pytest.mark.integration


@pytest.fixture
def loc_id(db_session):
    """Create a location and return its id (unique per test)."""
    lid = f"loc-repo-charger-{uuid.uuid4().hex[:8]}"
    loc = create_location(db_session, "Charger Repo Location", "1 Repo St", lid)
    return loc.id


def test_create_charger_and_get(db_session, loc_id):
    """create_charger then get_charger_by_charge_point_id returns the charger."""
    charger = create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-REPO-1",
        connection_url="ws://repo/ocpp",
        charger_name="Repo Charger",
        ocpp_version="1.6",
        evse_count=2,
    )
    assert charger.id is not None
    assert charger.charge_point_id == "CP-REPO-1"
    found = get_charger_by_charge_point_id(db_session, "CP-REPO-1")
    assert found is not None
    assert found.id == charger.id


def test_get_charger_by_charge_point_id_not_found(db_session):
    """get_charger_by_charge_point_id returns None for unknown id."""
    assert get_charger_by_charge_point_id(db_session, "CP-NONE") is None


def test_list_chargers_by_location(db_session, loc_id):
    """list_chargers_by_location returns chargers for that location."""
    create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-A",
        connection_url="ws://a/ocpp",
        charger_name="Charger A",
    )
    create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-B",
        connection_url="ws://b/ocpp",
        charger_name="Charger B",
    )
    chargers = list_chargers_by_location(db_session, loc_id)
    assert len(chargers) >= 2
    ids = [c.charge_point_id for c in chargers]
    assert "CP-A" in ids and "CP-B" in ids


def test_update_charger(db_session, loc_id):
    """update_charger updates fields and returns the charger."""
    create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-UPD",
        connection_url="ws://x/ocpp",
        charger_name="Original",
    )
    updated = update_charger(
        db_session,
        "CP-UPD",
        charger_name="Updated Name",
        connection_url="ws://y/ocpp",
    )
    assert updated is not None
    assert updated.charger_name == "Updated Name"
    assert updated.connection_url == "ws://y/ocpp"


def test_update_charger_not_found(db_session):
    """update_charger returns None for unknown charge_point_id."""
    assert update_charger(db_session, "CP-NONE", charger_name="X") is None


def test_update_charger_config(db_session, loc_id):
    """update_charger_config merges config and returns charger."""
    create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-CFG",
        connection_url="ws://x/ocpp",
        charger_name="Config Charger",
    )
    updated = update_charger_config(db_session, "CP-CFG", {"HeartbeatInterval": 60})
    assert updated is not None
    assert updated.config.get("HeartbeatInterval") == 60


def test_update_charger_config_not_found(db_session):
    """update_charger_config returns None for unknown charge_point_id."""
    assert update_charger_config(db_session, "CP-NONE", {"HeartbeatInterval": 60}) is None


def test_delete_charger(db_session, loc_id):
    """delete_charger removes charger and returns True."""
    create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-DEL",
        connection_url="ws://x/ocpp",
        charger_name="To Delete",
    )
    assert delete_charger(db_session, "CP-DEL") is True
    assert get_charger_by_charge_point_id(db_session, "CP-DEL") is None


def test_delete_charger_not_found(db_session):
    """delete_charger returns False for unknown charge_point_id."""
    assert delete_charger(db_session, "CP-NONE") is False


def test_count_chargers_by_location(db_session, loc_id):
    """count_chargers_by_location returns correct count."""
    create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-CNT1",
        connection_url="ws://x/ocpp",
        charger_name="C1",
    )
    create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-CNT2",
        connection_url="ws://x/ocpp",
        charger_name="C2",
    )
    assert count_chargers_by_location(db_session, loc_id) >= 2


def test_list_all_chargers(db_session, loc_id):
    """list_all_chargers returns all chargers."""
    create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-ALL",
        connection_url="ws://x/ocpp",
        charger_name="All Charger",
    )
    all_chargers = list_all_chargers(db_session)
    ids = [c.charge_point_id for c in all_chargers]
    assert "CP-ALL" in ids


def test_list_evses_by_charger_id(db_session, loc_id):
    """list_evses_by_charger_id returns EVSEs for the charger."""
    charger = create_charger(
        db_session,
        location_id=loc_id,
        charge_point_id="CP-EVSE",
        connection_url="ws://x/ocpp",
        charger_name="EVSE Charger",
        evse_count=3,
    )
    evses = list_evses_by_charger_id(db_session, charger.id)
    assert len(evses) == 3
    evse_ids = [e.evse_id for e in evses]
    assert evse_ids == [1, 2, 3]
