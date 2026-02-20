"""Tests for OCPP Authorize workflow: OCPPAuthorizationEnabled True/False and start_transaction flow."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from ocpp.v16 import call_result, datatypes
from ocpp.v16.enums import AuthorizationStatus

from simulator_core.charger import Charger
from simulator_core.evse import EVSE, EvseState
from simulator_core.ocpp_client import SimulatorChargePoint

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_connection():
    """Minimal connection mock for ChargePoint."""
    return AsyncMock()


def _auth_resp(accepted: bool):
    status = AuthorizationStatus.accepted if accepted else AuthorizationStatus.invalid
    return call_result.AuthorizePayload(id_tag_info=datatypes.IdTagInfo(status=status))


def _start_resp(transaction_id: int = 1, accepted: bool = True):
    status = AuthorizationStatus.accepted if accepted else AuthorizationStatus.invalid
    return call_result.StartTransactionPayload(
        transaction_id=transaction_id,
        id_tag_info=datatypes.IdTagInfo(status=status),
    )


@pytest.fixture
def charger_auth_enabled():
    """Charger with OCPPAuthorizationEnabled True."""
    return Charger(
        charge_point_id="CP_AUTH",
        evses=[EVSE(evse_id=1, max_power_W=22000.0)],
        config={
            "HeartbeatInterval": 120,
            "MeterValuesSampleInterval": 30,
            "OCPPAuthorizationEnabled": True,
        },
    )


@pytest.fixture
def charger_auth_disabled():
    """Charger with OCPPAuthorizationEnabled False (FreeVend)."""
    return Charger(
        charge_point_id="CP_FREE",
        evses=[EVSE(evse_id=1, max_power_W=22000.0)],
        config={
            "HeartbeatInterval": 120,
            "MeterValuesSampleInterval": 30,
            "OCPPAuthorizationEnabled": False,
        },
    )


@pytest.fixture
def charge_point_auth_enabled(mock_connection, charger_auth_enabled):
    cp = SimulatorChargePoint("CP_AUTH", mock_connection)
    cp.set_charger(charger_auth_enabled)
    return cp


@pytest.fixture
def charge_point_auth_disabled(mock_connection, charger_auth_disabled):
    cp = SimulatorChargePoint("CP_FREE", mock_connection)
    cp.set_charger(charger_auth_disabled)
    return cp


async def _dummy_meter_task():
    await asyncio.sleep(999)


@pytest.mark.asyncio
async def test_authorize_enabled_then_start_accepted(charge_point_auth_enabled):
    """When OCPPAuthorizationEnabled True: Authorize then StartTransaction; both Accepted -> charging starts."""
    # StatusNotification (Preparing), Authorize, StartTransaction, StatusNotification (Charging)
    status_resp = call_result.StatusNotificationPayload()
    responses = [
        status_resp,
        _auth_resp(accepted=True),
        _start_resp(transaction_id=42, accepted=True),
        status_resp,
    ]
    call_responses = iter(responses)

    async def mock_call(req):
        return next(call_responses)

    with patch.object(charge_point_auth_enabled, "call", side_effect=mock_call), patch(
        "simulator_core.ocpp_client.start_metering_loop"
    ) as mock_meter:
        meter_task = asyncio.create_task(_dummy_meter_task())
        mock_meter.return_value = (meter_task, asyncio.Event())
        try:
            result = await charge_point_auth_enabled.start_transaction(connector_id=1, id_tag="TAG1")
        finally:
            meter_task.cancel()
            try:
                await meter_task
            except asyncio.CancelledError:
                pass

    assert result == 42
    evse = charge_point_auth_enabled._charger.get_evse(1)
    assert evse.transaction_id == 42
    assert evse.state == EvseState.Charging
    assert mock_meter.called


@pytest.mark.asyncio
async def test_authorize_enabled_authorize_invalid_then_available(charge_point_auth_enabled):
    """When OCPPAuthorizationEnabled True and Authorize returns Invalid: no StartTransaction, EVSE back to Available."""
    status_resp = call_result.StatusNotificationPayload()
    responses = [
        status_resp,
        _auth_resp(accepted=False),
        status_resp,
    ]
    call_responses = iter(responses)

    async def mock_call(req):
        return next(call_responses)

    with patch.object(charge_point_auth_enabled, "call", side_effect=mock_call), patch(
        "simulator_core.ocpp_client.start_metering_loop"
    ) as mock_meter:
        result = await charge_point_auth_enabled.start_transaction(connector_id=1, id_tag="TAG1")

    assert result is None
    evse = charge_point_auth_enabled._charger.get_evse(1)
    assert evse.transaction_id is None
    assert evse.state == EvseState.Available
    mock_meter.assert_not_called()


@pytest.mark.asyncio
async def test_authorize_disabled_free_vend_start_accepted(charge_point_auth_disabled):
    """When OCPPAuthorizationEnabled False: no Authorize; StartTransaction only; Accepted -> charging starts."""
    status_resp = call_result.StatusNotificationPayload()
    responses = [
        status_resp,
        _start_resp(transaction_id=7, accepted=True),
        status_resp,
    ]
    call_responses = iter(responses)

    async def mock_call(req):
        return next(call_responses)

    with patch.object(charge_point_auth_disabled, "call", side_effect=mock_call), patch(
        "simulator_core.ocpp_client.start_metering_loop"
    ) as mock_meter:
        meter_task = asyncio.create_task(_dummy_meter_task())
        mock_meter.return_value = (meter_task, asyncio.Event())
        try:
            result = await charge_point_auth_disabled.start_transaction(connector_id=1, id_tag="TAG1")
        finally:
            meter_task.cancel()
            try:
                await meter_task
            except asyncio.CancelledError:
                pass

    assert result == 7
    evse = charge_point_auth_disabled._charger.get_evse(1)
    assert evse.transaction_id == 7
    assert evse.state == EvseState.Charging
    mock_meter.assert_called_once()


@pytest.mark.asyncio
async def test_authorize_disabled_start_invalid_reverts_to_available(charge_point_auth_disabled):
    """When OCPPAuthorizationEnabled False and StartTransaction returns Invalid: EVSE reverts to Available."""
    status_resp = call_result.StatusNotificationPayload()
    responses = [
        status_resp,
        _start_resp(transaction_id=0, accepted=False),
        status_resp,
    ]
    call_responses = iter(responses)

    async def mock_call(req):
        return next(call_responses)

    with patch.object(charge_point_auth_disabled, "call", side_effect=mock_call), patch(
        "simulator_core.ocpp_client.start_metering_loop"
    ) as mock_meter:
        result = await charge_point_auth_disabled.start_transaction(connector_id=1, id_tag="TAG1")

    assert result is None
    evse = charge_point_auth_disabled._charger.get_evse(1)
    assert evse.transaction_id is None
    assert evse.state == EvseState.Available
    mock_meter.assert_not_called()
