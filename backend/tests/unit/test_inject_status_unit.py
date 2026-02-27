"""Unit tests: send_status_notification extended signature (error_code, info, vendor_error_code)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.unit


def _make_cp():
    """Create a SimulatorChargePoint with a mocked WebSocket connection."""
    from simulator_core.ocpp_client import SimulatorChargePoint
    mock_conn = MagicMock()
    mock_conn.open = True
    return SimulatorChargePoint("CP-UNIT-TEST", mock_conn)


async def _call_send(cp, connector_id, status, **kwargs):
    """Helper: patch self.call and invoke send_status_notification, returning the payload."""
    captured = {}

    async def _capture(req):
        captured["req"] = req

    with patch.object(cp, "call", side_effect=_capture):
        await cp.send_status_notification(connector_id, status, **kwargs)
    return captured["req"]


# ---------------------------------------------------------------------------
# Default behaviour (backwards compatibility)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_error_code_is_no_error():
    """Omitting error_code defaults to no_error — existing callers are unaffected."""
    from ocpp.v16.enums import ChargePointErrorCode
    from simulator_core.evse import EvseState

    cp = _make_cp()
    req = await _call_send(cp, 1, EvseState.Available)
    assert req.error_code == ChargePointErrorCode.no_error


@pytest.mark.asyncio
async def test_no_info_no_vendor_by_default():
    """Without info/vendor_error_code, payload fields are None."""
    from simulator_core.evse import EvseState

    cp = _make_cp()
    req = await _call_send(cp, 1, EvseState.Available)
    assert getattr(req, "info", None) is None
    assert getattr(req, "vendor_error_code", None) is None


# ---------------------------------------------------------------------------
# Extended params forwarded correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passes_error_code():
    """Provided error_code is forwarded to the OCPP payload."""
    from ocpp.v16.enums import ChargePointErrorCode
    from simulator_core.evse import EvseState

    cp = _make_cp()
    req = await _call_send(
        cp, 1, EvseState.Faulted,
        error_code=ChargePointErrorCode.internal_error,
    )
    assert req.error_code == ChargePointErrorCode.internal_error


@pytest.mark.asyncio
async def test_passes_info():
    """Provided info string is forwarded to the OCPP payload."""
    from ocpp.v16.enums import ChargePointErrorCode
    from simulator_core.evse import EvseState

    cp = _make_cp()
    req = await _call_send(
        cp, 1, EvseState.Faulted,
        error_code=ChargePointErrorCode.ground_failure,
        info="Thermal runaway detected",
    )
    assert req.info == "Thermal runaway detected"


@pytest.mark.asyncio
async def test_passes_vendor_error_code():
    """Provided vendor_error_code is forwarded to the OCPP payload."""
    from ocpp.v16.enums import ChargePointErrorCode
    from simulator_core.evse import EvseState

    cp = _make_cp()
    req = await _call_send(
        cp, 1, EvseState.Faulted,
        error_code=ChargePointErrorCode.internal_error,
        vendor_error_code="VE-42",
    )
    assert req.vendor_error_code == "VE-42"


@pytest.mark.asyncio
async def test_passes_all_extended_params_together():
    """error_code, info, and vendor_error_code all forwarded correctly."""
    from ocpp.v16.enums import ChargePointErrorCode
    from simulator_core.evse import EvseState

    cp = _make_cp()
    req = await _call_send(
        cp, 2, EvseState.Faulted,
        error_code=ChargePointErrorCode.over_voltage,
        info="voltage spike",
        vendor_error_code="OV-001",
    )
    assert req.error_code == ChargePointErrorCode.over_voltage
    assert req.info == "voltage spike"
    assert req.vendor_error_code == "OV-001"
    assert req.connector_id == 2


@pytest.mark.asyncio
async def test_correct_ocpp_status_mapped():
    """EVSE state is correctly mapped to OCPP ChargePointStatus in the payload."""
    from ocpp.v16.enums import ChargePointStatus
    from simulator_core.evse import EvseState

    cp = _make_cp()
    req = await _call_send(cp, 1, EvseState.Unavailable)
    assert req.status == ChargePointStatus.unavailable
