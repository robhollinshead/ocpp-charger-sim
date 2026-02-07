"""In-memory charger store: single source of truth for API."""
from typing import Optional

from simulator_core.charger import Charger
from simulator_core.evse import EVSE


_store: dict[str, Charger] = {}


def get_all() -> list[Charger]:
    """List all chargers."""
    return list(_store.values())


def get_by_id(charge_point_id: str) -> Optional[Charger]:
    """Get charger by id or None."""
    return _store.get(charge_point_id)


def add(charger: Charger) -> None:
    """Add or replace charger by charge_point_id."""
    _store[charger.charge_point_id] = charger


def remove(charge_point_id: str) -> bool:
    """Remove charger by id. Returns True if removed."""
    if charge_point_id in _store:
        del _store[charge_point_id]
        return True
    return False


def remove_by_location_id(location_id: str) -> list[str]:
    """Remove all chargers associated with the given location. Returns list of removed charge_point_ids."""
    to_remove = [
        cid for cid, c in _store.items()
        if getattr(c, "location_id", None) == location_id
    ]
    for cid in to_remove:
        del _store[cid]
    return to_remove


def clear() -> None:
    """Clear all chargers (tests)."""
    _store.clear()


def seed_default() -> None:
    """Optionally seed one charger with 2 EVSEs so GET /chargers returns data."""
    if _store:
        return
    evses = [
        EVSE(evse_id=1, max_power_W=22000.0, voltage_V=230.0),
        EVSE(evse_id=2, max_power_W=22000.0, voltage_V=230.0),
    ]
    charger = Charger(
        charge_point_id="CP_001",
        evses=evses,
        config={"meter_interval_s": 10.0, "voltage_V": 230.0},
    )
    add(charger)
