"""Unit tests: offline mode — ConnectivityMode, CachedMessage, TxDefaultPowerW, meter loop caching."""
import asyncio

import pytest

from simulator_core.charger import CachedMessage, Charger, ConnectivityMode
from simulator_core.evse import EVSE, EvseState
from simulator_core.meter_engine import start_metering_loop

pytestmark = pytest.mark.unit


def _make_charger(**kwargs) -> Charger:
    """Helper: create a minimal Charger for testing."""
    return Charger(charge_point_id=kwargs.pop("charge_point_id", "TEST-001"), **kwargs)


# ---------------------------------------------------------------------------
# ConnectivityMode / set_offline / set_online
# ---------------------------------------------------------------------------


def test_charger_starts_online():
    charger = _make_charger()
    assert not charger.is_offline_mode()
    assert charger._connectivity_mode == ConnectivityMode.ONLINE


def test_set_offline_changes_mode():
    charger = _make_charger()
    charger.set_offline()
    assert charger.is_offline_mode()
    assert charger._connectivity_mode == ConnectivityMode.OFFLINE


def test_set_online_clears_offline_mode():
    charger = _make_charger()
    charger.set_offline()
    charger.set_online()
    assert not charger.is_offline_mode()
    assert charger._connectivity_mode == ConnectivityMode.ONLINE


def test_set_offline_idempotent():
    charger = _make_charger()
    charger.set_offline()
    charger.set_offline()  # calling again must not raise
    assert charger.is_offline_mode()


def test_set_online_idempotent():
    charger = _make_charger()
    charger.set_online()  # already online
    assert not charger.is_offline_mode()


# ---------------------------------------------------------------------------
# Message cache
# ---------------------------------------------------------------------------


def _cached_msg(msg_type: str = "StatusNotification") -> CachedMessage:
    return CachedMessage(
        message_type=msg_type,
        payload=object(),
        connector_id=1,
        local_transaction_id=None,
        timestamp="2026-01-01T00:00:00.000Z",
    )


def test_cache_message_appends():
    charger = _make_charger()
    msg = _cached_msg()
    charger.cache_message(msg)
    assert len(charger.get_message_cache()) == 1
    assert charger.get_message_cache()[0] is msg


def test_pop_message_cache_returns_all_and_clears():
    charger = _make_charger()
    charger.cache_message(_cached_msg("StatusNotification"))
    charger.cache_message(_cached_msg("MeterValues"))
    charger.cache_message(_cached_msg("StopTransaction"))
    drained = charger.pop_message_cache()
    assert len(drained) == 3
    assert [m.message_type for m in drained] == ["StatusNotification", "MeterValues", "StopTransaction"]
    assert charger.pop_message_cache() == []


def test_get_message_cache_does_not_clear():
    charger = _make_charger()
    charger.cache_message(_cached_msg())
    _ = charger.get_message_cache()
    assert len(charger.get_message_cache()) == 1


def test_cache_preserves_order():
    charger = _make_charger()
    types = ["StartTransaction", "MeterValues", "MeterValues", "StopTransaction"]
    for t in types:
        charger.cache_message(_cached_msg(t))
    assert [m.message_type for m in charger.pop_message_cache()] == types


# ---------------------------------------------------------------------------
# Offline transaction ID generation
# ---------------------------------------------------------------------------


def test_offline_tx_ids_are_negative_and_sequential():
    charger = _make_charger()
    assert charger.next_offline_transaction_id() == -1
    assert charger.next_offline_transaction_id() == -2
    assert charger.next_offline_transaction_id() == -3


def test_offline_tx_counter_is_independent_per_charger():
    c1 = _make_charger(charge_point_id="CP-1")
    c2 = _make_charger(charge_point_id="CP-2")
    c1.next_offline_transaction_id()
    c1.next_offline_transaction_id()
    assert c2.next_offline_transaction_id() == -1  # c2's counter starts fresh


# ---------------------------------------------------------------------------
# TxDefaultPowerW
# ---------------------------------------------------------------------------


def test_evse_default_tx_power_w_is_7400():
    evse = EVSE(evse_id=1)
    assert evse.tx_default_power_W == 7400.0


def test_get_effective_power_w_no_override_returns_zero():
    """Without a limit_W_override (no active profile), no power is delivered."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.Charging
    assert evse.get_effective_power_W() == 0.0


def test_get_effective_power_w_override_used_when_charging():
    """limit_W_override is used directly when EVSE is Charging."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.Charging
    assert evse.get_effective_power_W(limit_W_override=22000.0) == 22000.0


def test_get_effective_power_w_override_ignored_when_suspended():
    """limit_W_override is ignored when EVSE is suspended."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.SuspendedEVSE
    assert evse.get_effective_power_W(limit_W_override=22000.0) == 0.0


def test_get_effective_power_w_suspended_returns_zero():
    evse = EVSE(evse_id=1)
    evse.state = EvseState.SuspendedEV
    evse.offered_limit_W = 22000.0
    evse.tx_default_power_W = 7400.0
    assert evse.get_effective_power_W() == 0.0


def test_charger_propagates_tx_default_power_to_evses():
    evse = EVSE(evse_id=1)
    charger = Charger(
        charge_point_id="CP-1",
        evses=[evse],
        config={"TxDefaultPowerW": 11000.0},
    )
    assert evse.tx_default_power_W == 11000.0


def test_charger_get_tx_default_power_w():
    charger = Charger(charge_point_id="CP-1", config={"TxDefaultPowerW": 15000.0})
    assert charger.get_tx_default_power_w() == 15000.0


def test_charger_get_tx_default_power_w_fallback():
    charger = Charger(charge_point_id="CP-1")
    assert charger.get_tx_default_power_w() == 7400.0


# ---------------------------------------------------------------------------
# Meter loop caches messages when offline
# ---------------------------------------------------------------------------


async def test_meter_loop_continues_and_caches_when_offline():
    """Meter loop keeps running; send_cb caches instead of sending when charger is offline."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.Charging
    evse.transaction_id = -1
    evse.start_transaction(-1, "TEST_TAG", start_soc_pct=20.0, battery_capacity_wh=100.0)

    charger = _make_charger()
    charger.set_offline()

    async def send_cb(payload) -> None:
        charger.cache_message(
            CachedMessage(
                message_type="MeterValues",
                payload=payload,
                connector_id=1,
                local_transaction_id=-1,
                timestamp="2026-01-01T00:00:00.000Z",
            )
        )

    task, stop_event = start_metering_loop(
        evse, send_cb, ["Energy.Active.Import.Register", "Power.Active.Import"], interval_s=0.05,
        limit_fn=lambda: 7400.0,
    )
    # Allow at least 2 meter ticks
    await asyncio.sleep(0.15)
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    cached = charger.get_message_cache()
    assert len(cached) >= 2, f"Expected >= 2 cached MeterValues, got {len(cached)}"
    assert all(m.message_type == "MeterValues" for m in cached)
    # Meter must have advanced even though we were offline
    assert evse.energy_Wh > 0.0


async def test_meter_loop_without_limit_fn_delivers_no_power():
    """Without a limit_fn (no charging profile), the meter loop delivers zero power."""
    evse = EVSE(evse_id=1)
    evse.state = EvseState.Charging
    evse.transaction_id = 1
    evse.start_transaction(1, "TAG", start_soc_pct=20.0, battery_capacity_wh=100.0)

    sent = []

    async def send_cb(payload) -> None:
        sent.append(payload)

    task, stop_event = start_metering_loop(
        evse, send_cb, ["Power.Active.Import"], interval_s=0.05
    )
    await asyncio.sleep(0.08)
    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(sent) >= 1
    # No profile → no power delivered
    assert evse.power_W == pytest.approx(0.0)
