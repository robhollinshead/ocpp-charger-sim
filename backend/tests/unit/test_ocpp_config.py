"""Tests for OCPP GetConfiguration and ChangeConfiguration handlers."""
from unittest.mock import AsyncMock, patch

import pytest

from ocpp.v16.enums import ConfigurationStatus
from simulator_core.charger import Charger
from simulator_core.evse import EVSE
from simulator_core.ocpp_client import SimulatorChargePoint

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_connection():
    """Minimal connection mock; handlers under test don't send calls."""
    return AsyncMock()


@pytest.fixture
def charger_with_config():
    """Charger with known config keys."""
    return Charger(
        charge_point_id="CP_TEST",
        evses=[EVSE(evse_id=1, max_power_W=22000.0)],
        config={
            "HeartbeatInterval": 120,
            "ConnectionTimeOut": 60,
            "MeterValuesSampleInterval": 30,
            "ClockAlignedDataInterval": 900,
            "AuthorizeRemoteTxRequests": True,
            "LocalAuthListEnabled": True,
            "OCPPAuthorizationEnabled": True,
        },
    )


@pytest.fixture
def charge_point(mock_connection, charger_with_config):
    """SimulatorChargePoint with charger set."""
    cp = SimulatorChargePoint("CP_TEST", mock_connection)
    cp.set_charger(charger_with_config)
    return cp


@pytest.mark.asyncio
async def test_get_configuration_no_keys_returns_all_known(charge_point):
    """GetConfiguration with no keys returns all known config keys."""
    result = await charge_point.on_get_configuration(key=None)
    assert result is not None
    keys_returned = [kv.key for kv in result.configuration_key]
    assert "HeartbeatInterval" in keys_returned
    assert "AuthorizeRemoteTxRequests" in keys_returned
    assert "OCPPAuthorizationEnabled" in keys_returned
    assert result.unknown_key == []


@pytest.mark.asyncio
async def test_get_configuration_specific_keys(charge_point):
    """GetConfiguration with specific keys returns those known and unknown_key for rest."""
    result = await charge_point.on_get_configuration(key=["HeartbeatInterval", "UnknownKey", "MeterValuesSampleInterval"])
    assert result is not None
    keys_returned = [kv.key for kv in result.configuration_key]
    assert "HeartbeatInterval" in keys_returned
    assert "MeterValuesSampleInterval" in keys_returned
    assert "UnknownKey" not in keys_returned
    assert "UnknownKey" in result.unknown_key


@pytest.mark.asyncio
async def test_get_configuration_values_serialized(charge_point):
    """GetConfiguration returns string values and readonly=False."""
    result = await charge_point.on_get_configuration(key=["HeartbeatInterval", "AuthorizeRemoteTxRequests"])
    assert result is not None
    for kv in result.configuration_key:
        assert kv.readonly is False
        if kv.key == "HeartbeatInterval":
            assert kv.value == "120"
        if kv.key == "AuthorizeRemoteTxRequests":
            assert kv.value == "true"


@pytest.mark.asyncio
async def test_get_configuration_no_charger_returns_empty(mock_connection):
    """GetConfiguration with no charger set returns empty configuration_key."""
    cp = SimulatorChargePoint("CP_TEST", mock_connection)
    result = await cp.on_get_configuration(key=None)
    assert result.configuration_key == []
    assert result.unknown_key == []


@pytest.mark.asyncio
async def test_change_configuration_accepted_updates_memory(charge_point):
    """ChangeConfiguration with valid key/value returns Accepted and updates in-memory config."""
    with patch("simulator_core.ocpp_client.persist_charger_config"):
        result = await charge_point.on_change_configuration(key="HeartbeatInterval", value="60")
    assert result.status == ConfigurationStatus.accepted
    assert charge_point._charger.config["HeartbeatInterval"] == 60


@pytest.mark.asyncio
async def test_change_configuration_boolean(charge_point):
    """ChangeConfiguration accepts boolean-like values."""
    with patch("simulator_core.ocpp_client.persist_charger_config"):
        await charge_point.on_change_configuration(key="AuthorizeRemoteTxRequests", value="false")
    assert charge_point._charger.config["AuthorizeRemoteTxRequests"] is False


@pytest.mark.asyncio
async def test_change_configuration_unknown_key_not_supported(charge_point):
    """ChangeConfiguration with unknown key returns NotSupported."""
    with patch("simulator_core.ocpp_client.persist_charger_config") as mock_persist:
        result = await charge_point.on_change_configuration(key="UnknownKey", value="1")
    assert result.status == ConfigurationStatus.not_supported
    mock_persist.assert_not_called()


@pytest.mark.asyncio
async def test_change_configuration_invalid_int_rejected(charge_point):
    """ChangeConfiguration with invalid integer value returns Rejected."""
    with patch("simulator_core.ocpp_client.persist_charger_config"):
        result = await charge_point.on_change_configuration(key="HeartbeatInterval", value="not_a_number")
    assert result.status == ConfigurationStatus.rejected
    assert charge_point._charger.config["HeartbeatInterval"] == 120  # unchanged


@pytest.mark.asyncio
async def test_change_configuration_invalid_bool_rejected(charge_point):
    """ChangeConfiguration with invalid boolean value returns Rejected."""
    with patch("simulator_core.ocpp_client.persist_charger_config"):
        result = await charge_point.on_change_configuration(key="LocalAuthListEnabled", value="maybe")
    assert result.status == ConfigurationStatus.rejected


@pytest.mark.asyncio
async def test_change_configuration_no_charger_rejected(mock_connection):
    """ChangeConfiguration with no charger set returns Rejected."""
    cp = SimulatorChargePoint("CP_TEST", mock_connection)
    result = await cp.on_change_configuration(key="HeartbeatInterval", value="60")
    assert result.status == ConfigurationStatus.rejected


@pytest.mark.asyncio
async def test_change_configuration_ocpp_authorization_enabled(charge_point):
    """ChangeConfiguration accepts OCPPAuthorizationEnabled (boolean)."""
    with patch("simulator_core.ocpp_client.persist_charger_config"):
        await charge_point.on_change_configuration(key="OCPPAuthorizationEnabled", value="false")
    assert charge_point._charger.config["OCPPAuthorizationEnabled"] is False
