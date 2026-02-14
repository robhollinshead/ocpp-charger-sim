"""Unit tests: config_sync (persist_charger_config)."""
from unittest.mock import MagicMock, patch

import pytest

from simulator_core.config_sync import persist_charger_config

pytestmark = pytest.mark.unit


def test_persist_charger_config_calls_update():
    """persist_charger_config calls update_charger_config with session."""
    mock_db = MagicMock()
    with patch("simulator_core.config_sync.SessionLocal", return_value=mock_db):
        with patch("simulator_core.config_sync.update_charger_config") as mock_update:
            mock_update.return_value = MagicMock()
            persist_charger_config("CP-SYNC", {"HeartbeatInterval": 60})
            mock_update.assert_called_once()
            assert mock_update.call_args[0][1] == "CP-SYNC"
            assert mock_update.call_args[0][2] == {"HeartbeatInterval": 60}
    mock_db.close.assert_called_once()


def test_persist_charger_config_handles_not_found():
    """persist_charger_config closes db when charger not found."""
    mock_db = MagicMock()
    with patch("simulator_core.config_sync.SessionLocal", return_value=mock_db):
        with patch("simulator_core.config_sync.update_charger_config", return_value=None):
            persist_charger_config("CP-NONE", {"HeartbeatInterval": 60})
    mock_db.close.assert_called_once()


def test_persist_charger_config_closes_db_on_exception():
    """persist_charger_config closes db even when update raises."""
    mock_db = MagicMock()
    with patch("simulator_core.config_sync.SessionLocal", return_value=mock_db):
        with patch("simulator_core.config_sync.update_charger_config", side_effect=RuntimeError("db error")):
            persist_charger_config("CP-ERR", {})
    mock_db.close.assert_called_once()
