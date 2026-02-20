"""Unit tests: simulator_core store (in-memory charger store)."""
import pytest

from simulator_core.charger import Charger
from simulator_core.evse import EVSE
from simulator_core.store import add, clear, get_all, get_by_id, remove, remove_by_location_id, seed_default

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clear_store():
    """Clear store before and after each test so tests don't leak state."""
    clear()
    yield
    clear()


def test_add_and_get_by_id():
    """add then get_by_id returns the charger."""
    evse = EVSE(evse_id=1, max_power_W=22000.0)
    charger = Charger(charge_point_id="CP-STORE-1", evses=[evse], config={})
    add(charger)
    found = get_by_id("CP-STORE-1")
    assert found is charger


def test_get_by_id_missing():
    """get_by_id returns None for unknown id."""
    assert get_by_id("CP-NONE") is None


def test_remove_existing():
    """remove returns True and charger is gone."""
    charger = Charger(charge_point_id="CP-RM", evses=[], config={})
    add(charger)
    assert remove("CP-RM") is True
    assert get_by_id("CP-RM") is None


def test_remove_missing():
    """remove returns False for unknown id."""
    assert remove("CP-NONE") is False


def test_get_all():
    """get_all returns list of all chargers."""
    add(Charger(charge_point_id="CP-A", evses=[], config={}))
    add(Charger(charge_point_id="CP-B", evses=[], config={}))
    all_chargers = get_all()
    ids = [c.charge_point_id for c in all_chargers]
    assert "CP-A" in ids and "CP-B" in ids


def test_remove_by_location_id():
    """remove_by_location_id removes chargers with that location_id and returns ids."""
    c1 = Charger(charge_point_id="CP-L1", evses=[], config={}, location_id="loc-1")
    c2 = Charger(charge_point_id="CP-L2", evses=[], config={}, location_id="loc-1")
    c3 = Charger(charge_point_id="CP-OTHER", evses=[], config={}, location_id="loc-2")
    add(c1)
    add(c2)
    add(c3)
    removed = remove_by_location_id("loc-1")
    assert set(removed) == {"CP-L1", "CP-L2"}
    assert get_by_id("CP-L1") is None
    assert get_by_id("CP-L2") is None
    assert get_by_id("CP-OTHER") is not None


def test_seed_default_adds_one_charger():
    """seed_default adds one charger when store is empty."""
    seed_default()
    all_chargers = get_all()
    assert len(all_chargers) == 1
    assert all_chargers[0].charge_point_id == "CP_001"
    assert len(all_chargers[0].evses) == 2


def test_seed_default_idempotent_when_non_empty():
    """seed_default does nothing when store already has chargers."""
    add(Charger(charge_point_id="CP-EXISTING", evses=[], config={}))
    seed_default()
    assert get_by_id("CP_001") is None
    assert get_by_id("CP-EXISTING") is not None
