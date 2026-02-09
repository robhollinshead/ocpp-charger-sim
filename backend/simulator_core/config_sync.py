"""Sync charger config to DB from async OCPP handlers (e.g. ChangeConfiguration)."""
import logging

from db import SessionLocal
from repositories.charger_repository import update_charger_config

LOG = logging.getLogger(__name__)


def persist_charger_config(charge_point_id: str, config_updates: dict) -> None:
    """
    Merge config_updates into charger config in DB. Synchronous; run via asyncio.to_thread.
    Logs and swallows errors so the caller can still return Accepted for in-memory update.
    """
    db = SessionLocal()
    try:
        updated = update_charger_config(db, charge_point_id, config_updates)
        if updated is None:
            LOG.warning("persist_charger_config: charger not found for charge_point_id=%s", charge_point_id)
    except Exception as e:
        LOG.exception("persist_charger_config failed for %s: %s", charge_point_id, e)
    finally:
        db.close()
