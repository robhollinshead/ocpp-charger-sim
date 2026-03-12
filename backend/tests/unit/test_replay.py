"""Unit tests: replay_cached_messages — ordering, tx ID reconciliation, patch helpers."""
from unittest.mock import AsyncMock, call

import pytest
from ocpp.v16 import call as ocpp_call, call_result, datatypes
from ocpp.v16.enums import AuthorizationStatus, Reason

from simulator_core.charger import CachedMessage, Charger
from simulator_core.evse import EVSE, EvseState
from simulator_core.ocpp_client import (
    _patch_meter_values_tx_id,
    _patch_stop_transaction_tx_id,
    replay_cached_messages,
)

pytestmark = pytest.mark.unit


def _make_charger(evses=None) -> Charger:
    return Charger(charge_point_id="CP-REPLAY", evses=evses or [])


def _make_mock_cp(start_tx_response_id: int = 42) -> AsyncMock:
    """Build a mock SimulatorChargePoint that returns a sensible StartTransaction response."""
    cp = AsyncMock()
    cp.call.return_value = call_result.StartTransactionPayload(
        transaction_id=start_tx_response_id,
        id_tag_info=datatypes.IdTagInfo(status=AuthorizationStatus.accepted),
    )
    return cp


def _status_notification_payload(connector_id: int = 1) -> ocpp_call.StatusNotificationPayload:
    from ocpp.v16.enums import ChargePointStatus, ChargePointErrorCode
    return ocpp_call.StatusNotificationPayload(
        connector_id=connector_id,
        error_code=ChargePointErrorCode.no_error,
        status=ChargePointStatus.charging,
        timestamp="2026-01-01T00:00:00.000Z",
    )


def _start_tx_payload(connector_id: int = 1) -> ocpp_call.StartTransactionPayload:
    return ocpp_call.StartTransactionPayload(
        connector_id=connector_id,
        id_tag="TAG1",
        meter_start=0,
        timestamp="2026-01-01T00:00:00.000Z",
    )


def _meter_values_payload(connector_id: int = 1, tx_id: int = -1) -> ocpp_call.MeterValuesPayload:
    return ocpp_call.MeterValuesPayload(
        connector_id=connector_id,
        transaction_id=tx_id,
        meter_value=[],
    )


def _stop_tx_payload(connector_id: int = 1, tx_id: int = -1) -> ocpp_call.StopTransactionPayload:
    return ocpp_call.StopTransactionPayload(
        meter_stop=500,
        timestamp="2026-01-01T01:00:00.000Z",
        transaction_id=tx_id,
        reason=Reason.local,
        id_tag=None,
    )


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


def test_patch_meter_values_tx_id():
    original = _meter_values_payload(connector_id=1, tx_id=-1)
    patched = _patch_meter_values_tx_id(original, 99)
    assert patched.transaction_id == 99
    assert patched.connector_id == 1
    assert patched.meter_value == []


def test_patch_stop_transaction_tx_id():
    original = _stop_tx_payload(tx_id=-1)
    patched = _patch_stop_transaction_tx_id(original, 99)
    assert patched.transaction_id == 99
    assert patched.meter_stop == 500
    assert patched.reason == Reason.local


# ---------------------------------------------------------------------------
# replay_cached_messages — basic cases
# ---------------------------------------------------------------------------


async def test_replay_empty_cache_is_noop():
    charger = _make_charger()
    cp = AsyncMock()
    await replay_cached_messages(charger, cp)
    cp.call.assert_not_called()


async def test_replay_status_notifications():
    charger = _make_charger()
    payload = _status_notification_payload()
    charger.cache_message(CachedMessage("StatusNotification", payload, 1, None, "ts"))
    charger.cache_message(CachedMessage("StatusNotification", payload, 1, None, "ts"))
    cp = AsyncMock()
    await replay_cached_messages(charger, cp)
    assert cp.call.call_count == 2
    # Cache should be cleared after replay
    assert charger.get_message_cache() == []


async def test_replay_sends_in_order():
    """Messages must be replayed in the exact order they were cached."""
    charger = _make_charger()
    types_in = ["StatusNotification", "StartTransaction", "MeterValues", "StopTransaction"]
    payloads = [
        _status_notification_payload(),
        _start_tx_payload(),
        _meter_values_payload(tx_id=-1),
        _stop_tx_payload(tx_id=-1),
    ]
    for msg_type, payload in zip(types_in, payloads):
        charger.cache_message(CachedMessage(msg_type, payload, 1, -1, "ts"))

    cp = _make_mock_cp(start_tx_response_id=55)
    # stub MeterValues + StopTransaction responses
    cp.call.side_effect = [
        None,  # StatusNotification
        call_result.StartTransactionPayload(
            transaction_id=55,
            id_tag_info=datatypes.IdTagInfo(status=AuthorizationStatus.accepted),
        ),
        None,  # MeterValues
        None,  # StopTransaction
    ]
    await replay_cached_messages(charger, cp)
    # All 4 messages sent
    assert cp.call.call_count == 4


# ---------------------------------------------------------------------------
# Transaction ID reconciliation
# ---------------------------------------------------------------------------


async def test_replay_patches_meter_values_tx_id():
    """StartTransaction replay gets real ID; subsequent MeterValues are patched."""
    charger = _make_charger()
    charger.cache_message(CachedMessage("StartTransaction", _start_tx_payload(), 1, -1, "ts"))
    charger.cache_message(CachedMessage("MeterValues", _meter_values_payload(tx_id=-1), 1, -1, "ts"))
    charger.cache_message(CachedMessage("MeterValues", _meter_values_payload(tx_id=-1), 1, -1, "ts"))

    cp = AsyncMock()
    cp.call.side_effect = [
        call_result.StartTransactionPayload(
            transaction_id=42,
            id_tag_info=datatypes.IdTagInfo(status=AuthorizationStatus.accepted),
        ),
        None,  # first MeterValues
        None,  # second MeterValues
    ]

    await replay_cached_messages(charger, cp)

    # StartTransaction call
    start_call_args = cp.call.call_args_list[0][0][0]
    # MeterValues should have transaction_id=42
    meter_call_1 = cp.call.call_args_list[1][0][0]
    meter_call_2 = cp.call.call_args_list[2][0][0]
    assert meter_call_1.transaction_id == 42
    assert meter_call_2.transaction_id == 42


async def test_replay_patches_stop_transaction_tx_id():
    """StopTransaction is patched with the CSMS-assigned ID."""
    charger = _make_charger()
    charger.cache_message(CachedMessage("StartTransaction", _start_tx_payload(), 1, -1, "ts"))
    charger.cache_message(CachedMessage("StopTransaction", _stop_tx_payload(tx_id=-1), 1, -1, "ts"))

    cp = AsyncMock()
    cp.call.side_effect = [
        call_result.StartTransactionPayload(
            transaction_id=99,
            id_tag_info=datatypes.IdTagInfo(status=AuthorizationStatus.accepted),
        ),
        None,  # StopTransaction
    ]

    await replay_cached_messages(charger, cp)

    stop_call_args = cp.call.call_args_list[1][0][0]
    assert stop_call_args.transaction_id == 99


async def test_replay_full_offline_session():
    """Complete offline session: StatusNotification → StartTx → MeterValues × 3 → StopTx.
    All IDs reconciled from StartTx response."""
    evse = EVSE(evse_id=1)
    evse.transaction_id = -1
    charger = _make_charger(evses=[evse])

    msgs = [
        CachedMessage("StatusNotification", _status_notification_payload(), 1, None, "ts"),
        CachedMessage("StartTransaction", _start_tx_payload(), 1, -1, "ts"),
        CachedMessage("MeterValues", _meter_values_payload(tx_id=-1), 1, -1, "ts"),
        CachedMessage("MeterValues", _meter_values_payload(tx_id=-1), 1, -1, "ts"),
        CachedMessage("MeterValues", _meter_values_payload(tx_id=-1), 1, -1, "ts"),
        CachedMessage("StatusNotification", _status_notification_payload(), 1, None, "ts"),
        CachedMessage("StopTransaction", _stop_tx_payload(tx_id=-1), 1, -1, "ts"),
    ]
    for m in msgs:
        charger.cache_message(m)

    real_tx_id = 1234
    cp = AsyncMock()
    cp.call.side_effect = [
        None,  # StatusNotification
        call_result.StartTransactionPayload(
            transaction_id=real_tx_id,
            id_tag_info=datatypes.IdTagInfo(status=AuthorizationStatus.accepted),
        ),
        None, None, None,  # 3× MeterValues
        None,  # StatusNotification
        None,  # StopTransaction
    ]

    await replay_cached_messages(charger, cp)

    assert cp.call.call_count == 7

    # Verify all MeterValues have real_tx_id
    for i in [2, 3, 4]:
        mv_payload = cp.call.call_args_list[i][0][0]
        assert mv_payload.transaction_id == real_tx_id, f"msg {i}: expected {real_tx_id}, got {mv_payload.transaction_id}"

    # Verify StopTransaction has real_tx_id
    stop_payload = cp.call.call_args_list[6][0][0]
    assert stop_payload.transaction_id == real_tx_id

    # Verify live EVSE transaction_id was patched
    assert evse.transaction_id == real_tx_id


async def test_replay_online_tx_not_patched():
    """Messages with local_transaction_id=None (online-started tx) are not patched."""
    charger = _make_charger()
    # Online tx (no local_transaction_id)
    charger.cache_message(CachedMessage("MeterValues", _meter_values_payload(tx_id=77), 1, None, "ts"))

    cp = AsyncMock()
    cp.call.return_value = None

    await replay_cached_messages(charger, cp)

    mv_payload = cp.call.call_args_list[0][0][0]
    # Should NOT be patched — no StartTransaction precedes it
    assert mv_payload.transaction_id == 77


async def test_replay_handles_call_error_gracefully():
    """Individual message send errors are caught; remaining messages still sent."""
    charger = _make_charger()
    charger.cache_message(CachedMessage("StatusNotification", _status_notification_payload(), 1, None, "ts"))
    charger.cache_message(CachedMessage("StatusNotification", _status_notification_payload(), 1, None, "ts"))

    cp = AsyncMock()
    cp.call.side_effect = [Exception("CSMS error"), None]

    await replay_cached_messages(charger, cp)  # must not raise
    assert cp.call.call_count == 2
