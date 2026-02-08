"""Charger repository: list, get, create, update, delete."""
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.charger import Charger as ChargerModel
from models.evse import Evse as EvseModel
from schemas.chargers import DEFAULT_CHARGER_CONFIG


def create_charger(
    session: Session,
    *,
    location_id: str,
    charge_point_id: str,
    connection_url: str,
    charger_name: str,
    ocpp_version: str = "1.6",
    evse_count: int = 1,
    charge_point_vendor: str = "FastCharge",
    charge_point_model: str = "Pro 150",
    firmware_version: str = "2.4.1",
) -> ChargerModel:
    """Create a charger with evse_count EVSEs (evse_id 1..evse_count), commit, and return it."""
    charger = ChargerModel(
        location_id=location_id,
        charge_point_id=charge_point_id,
        connection_url=connection_url,
        charger_name=charger_name,
        ocpp_version=ocpp_version,
        charge_point_vendor=charge_point_vendor,
        charge_point_model=charge_point_model,
        firmware_version=firmware_version,
        config=dict(DEFAULT_CHARGER_CONFIG),
    )
    session.add(charger)
    session.flush()  # get charger.id before adding evses
    for i in range(1, evse_count + 1):
        session.add(EvseModel(charger_id=charger.id, evse_id=i))
    session.commit()
    session.refresh(charger)
    return charger


def get_charger_by_charge_point_id(session: Session, charge_point_id: str) -> Optional[ChargerModel]:
    """Return charger by charge_point_id or None."""
    return session.execute(
        select(ChargerModel).where(ChargerModel.charge_point_id == charge_point_id)
    ).scalar_one_or_none()


def list_chargers_by_location(session: Session, location_id: str) -> list[ChargerModel]:
    """Return all chargers for a location."""
    result = session.execute(
        select(ChargerModel)
        .where(ChargerModel.location_id == location_id)
        .order_by(ChargerModel.charger_name)
    )
    return list(result.scalars().all())


def update_charger(
    session: Session,
    charge_point_id: str,
    *,
    connection_url: Optional[str] = None,
    charger_name: Optional[str] = None,
    ocpp_version: Optional[str] = None,
) -> Optional[ChargerModel]:
    """Update charger by charge_point_id. Returns updated charger or None if not found."""
    charger = get_charger_by_charge_point_id(session, charge_point_id)
    if charger is None:
        return None
    if connection_url is not None:
        charger.connection_url = connection_url
    if charger_name is not None:
        charger.charger_name = charger_name
    if ocpp_version is not None:
        charger.ocpp_version = ocpp_version
    session.commit()
    session.refresh(charger)
    return charger


def update_charger_config(
    session: Session,
    charge_point_id: str,
    config_updates: dict[str, Any],
) -> Optional[ChargerModel]:
    """Merge config_updates into charger config and save. Returns updated charger or None."""
    charger = get_charger_by_charge_point_id(session, charge_point_id)
    if charger is None:
        return None
    current = charger.config or {}
    merged = {**current, **config_updates}
    charger.config = merged
    session.commit()
    session.refresh(charger)
    return charger


def delete_charger(session: Session, charge_point_id: str) -> bool:
    """Delete charger by charge_point_id. Returns True if deleted, False if not found."""
    charger = get_charger_by_charge_point_id(session, charge_point_id)
    if charger is None:
        return False
    session.delete(charger)
    session.commit()
    return True


def count_chargers_by_location(session: Session, location_id: str) -> int:
    """Return the number of chargers at a location."""
    result = session.execute(
        select(func.count()).select_from(ChargerModel).where(ChargerModel.location_id == location_id)
    )
    return result.scalar() or 0


def list_all_chargers(session: Session) -> list[ChargerModel]:
    """Return all chargers (for startup load)."""
    result = session.execute(select(ChargerModel).order_by(ChargerModel.location_id, ChargerModel.charger_name))
    return list(result.scalars().all())


def list_evses_by_charger_id(session: Session, charger_id: str) -> list[EvseModel]:
    """Return all EVSEs for a charger by charger id (UUID), ordered by evse_id."""
    result = session.execute(
        select(EvseModel).where(EvseModel.charger_id == charger_id).order_by(EvseModel.evse_id)
    )
    return list(result.scalars().all())
