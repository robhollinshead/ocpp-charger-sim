"""Unit tests for simulator_core.scenario_engine."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from simulator_core.evse import EvseState
from simulator_core.scenario_engine import (
    ScenarioRun,
    clear_all,
    clear_scenario,
    get_active_scenario,
    run_rush_period,
    set_active_scenario,
)


# ---------------------------------------------------------------------------
# Helpers to build fake chargers / EVSEs / vehicles
# ---------------------------------------------------------------------------

def _make_evse(evse_id: int, state: EvseState = EvseState.Available) -> MagicMock:
    evse = MagicMock()
    evse.evse_id = evse_id
    evse.state = state
    evse.transaction_id = None
    return evse


def _make_sim(charge_point_id: str, location_id: str, evses, *, connected: bool = True) -> MagicMock:
    sim = MagicMock()
    sim.charge_point_id = charge_point_id
    sim.location_id = location_id
    sim.evses = evses
    sim.is_connected = connected
    sim._ocpp_client = AsyncMock()
    sim._ocpp_client.start_transaction = AsyncMock(return_value=1)
    sim.clear_stop_connect = MagicMock()
    return sim


def _make_row(charge_point_id: str, connection_url: str = "ws://csms/ocpp") -> SimpleNamespace:
    return SimpleNamespace(
        charge_point_id=charge_point_id,
        connection_url=connection_url,
        security_profile="none",
        basic_auth_password=None,
    )


def _make_vehicle(id_tag: str, battery_kwh: float = 75.0) -> SimpleNamespace:
    """Vehicle row with .id_tags as plain strings (as returned by the repo)."""
    tag = SimpleNamespace(id_tag=id_tag)
    return SimpleNamespace(id_tags=[tag], battery_capacity_kwh=battery_kwh)


# ---------------------------------------------------------------------------
# In-memory store helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_scenario_store():
    """Clear the scenario store before and after each test."""
    clear_all()
    yield
    clear_all()


# ---------------------------------------------------------------------------
# Tests: pairing logic
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRushPeriodPairing:
    async def test_all_evses_and_vehicles_available(self):
        """All 3 EVSEs paired with 3 vehicles → 3 completed pairs."""
        evses = [_make_evse(1), _make_evse(2), _make_evse(3)]
        sim = _make_sim("CP-1", "loc-1", evses)
        vehicles = [_make_vehicle("tag-1"), _make_vehicle("tag-2"), _make_vehicle("tag-3")]
        charger_rows = [_make_row("CP-1")]

        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            run = await run_rush_period("loc-1", 3, charger_rows, vehicles, sleep_fn=no_sleep)

        assert run.status == "completed"
        assert run.total_pairs == 3
        assert run.completed_pairs == 3
        assert run.failed_pairs == 0

    async def test_limited_by_vehicles(self):
        """5 EVSEs but only 2 vehicles → 2 pairs."""
        evses = [_make_evse(i) for i in range(1, 6)]
        sim = _make_sim("CP-1", "loc-1", evses)
        vehicles = [_make_vehicle("tag-1"), _make_vehicle("tag-2")]
        charger_rows = [_make_row("CP-1")]

        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            run = await run_rush_period("loc-1", 2, charger_rows, vehicles, sleep_fn=no_sleep)

        assert run.total_pairs == 2
        assert run.completed_pairs == 2

    async def test_limited_by_evses(self):
        """2 EVSEs but 5 vehicles → 2 pairs."""
        evses = [_make_evse(1), _make_evse(2)]
        sim = _make_sim("CP-1", "loc-1", evses)
        vehicles = [_make_vehicle(f"tag-{i}") for i in range(1, 6)]
        charger_rows = [_make_row("CP-1")]

        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            run = await run_rush_period("loc-1", 2, charger_rows, vehicles, sleep_fn=no_sleep)

        assert run.total_pairs == 2
        assert run.completed_pairs == 2

    async def test_no_vehicles_completes_immediately(self):
        """No vehicles → scenario completes with 0 pairs."""
        evses = [_make_evse(1)]
        sim = _make_sim("CP-1", "loc-1", evses)
        charger_rows = [_make_row("CP-1")]

        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            run = await run_rush_period("loc-1", 5, charger_rows, [], sleep_fn=no_sleep)

        assert run.status == "completed"
        assert run.total_pairs == 0

    async def test_no_available_evses_completes_immediately(self):
        """All EVSEs are busy → scenario completes with 0 pairs."""
        busy_evse = _make_evse(1, state=EvseState.Charging)
        sim = _make_sim("CP-1", "loc-1", [busy_evse])
        vehicles = [_make_vehicle("tag-1")]
        charger_rows = [_make_row("CP-1")]

        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            run = await run_rush_period("loc-1", 5, charger_rows, vehicles, sleep_fn=no_sleep)

        assert run.status == "completed"
        assert run.total_pairs == 0

    async def test_vehicles_without_id_tags_skipped(self):
        """Vehicles with no id_tags are skipped."""
        evses = [_make_evse(1), _make_evse(2)]
        sim = _make_sim("CP-1", "loc-1", evses)
        valid_v = _make_vehicle("tag-1")
        no_tag_v = SimpleNamespace(id_tags=[], battery_capacity_kwh=50.0)
        charger_rows = [_make_row("CP-1")]

        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            run = await run_rush_period(
                "loc-1", 2, charger_rows, [valid_v, no_tag_v], sleep_fn=no_sleep
            )

        assert run.total_pairs == 1
        assert run.completed_pairs == 1


# ---------------------------------------------------------------------------
# Tests: connection handling
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRushPeriodConnection:
    async def test_skips_charger_that_fails_to_connect(self):
        """Charger that stays disconnected is added to offline_charger_ids."""
        evses = [_make_evse(1)]
        sim = _make_sim("CP-1", "loc-1", evses, connected=False)
        # Even after sleep, still not connected
        sim.is_connected = False
        vehicles = [_make_vehicle("tag-1")]
        charger_rows = [_make_row("CP-1")]

        fake_connect = AsyncMock()
        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            run = await run_rush_period(
                "loc-1", 2, charger_rows, vehicles,
                connect_fn=fake_connect, sleep_fn=no_sleep,
            )

        assert "CP-1" in run.offline_charger_ids
        assert run.total_pairs == 0
        assert run.status == "completed"

    async def test_already_connected_charger_not_reconnected(self):
        """Already-connected charger skips the connect step."""
        evses = [_make_evse(1)]
        sim = _make_sim("CP-1", "loc-1", evses, connected=True)
        vehicles = [_make_vehicle("tag-1")]
        charger_rows = [_make_row("CP-1")]

        fake_connect = AsyncMock()
        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            await run_rush_period(
                "loc-1", 1, charger_rows, vehicles,
                connect_fn=fake_connect, sleep_fn=no_sleep,
            )

        # connect_fn should NOT have been called (sleep is called from start_transaction wait,
        # but connect_fn itself should not be called for already-connected chargers)
        fake_connect.assert_not_called()

    async def test_charger_not_in_location_ignored(self):
        """Charger in a different location is not touched."""
        other_sim = _make_sim("CP-OTHER", "loc-99", [_make_evse(1)])
        vehicles = [_make_vehicle("tag-1")]
        charger_rows = []  # no rows for loc-1

        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [other_sim]
            run = await run_rush_period("loc-1", 1, charger_rows, vehicles, sleep_fn=no_sleep)

        assert run.total_pairs == 0


# ---------------------------------------------------------------------------
# Tests: timing / interval
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRushPeriodTiming:
    async def test_interval_between_plug_ins(self):
        """For 3 pairs over 6 minutes, sleep should be called twice with 120 s interval."""
        evses = [_make_evse(i) for i in range(1, 4)]
        sim = _make_sim("CP-1", "loc-1", evses)
        vehicles = [_make_vehicle(f"tag-{i}") for i in range(1, 4)]
        charger_rows = [_make_row("CP-1")]

        sleep_calls: list[float] = []

        async def tracking_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            await run_rush_period("loc-1", 6, charger_rows, vehicles, sleep_fn=tracking_sleep)

        # 3 pairs: sleep called 2 times (before 2nd and 3rd plug-in)
        assert len(sleep_calls) == 2
        expected_interval = (6 * 60) / 3  # 120 seconds
        for s in sleep_calls:
            assert abs(s - expected_interval) < 0.01

    async def test_single_pair_no_sleep_between_plug_ins(self):
        """With 1 pair, no inter-plug-in sleep is needed."""
        evses = [_make_evse(1)]
        sim = _make_sim("CP-1", "loc-1", evses)
        vehicles = [_make_vehicle("tag-1")]
        charger_rows = [_make_row("CP-1")]

        sleep_calls: list[float] = []

        async def tracking_sleep(secs: float) -> None:
            sleep_calls.append(secs)

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            await run_rush_period("loc-1", 5, charger_rows, vehicles, sleep_fn=tracking_sleep)

        # Only the connection-wait sleep (5.0 s for disconnected charger) would count,
        # but our sim is already connected, so no sleeps at all.
        assert sleep_calls == []


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRushPeriodErrors:
    async def test_transaction_failure_increments_failed_pairs(self):
        """If start_transaction raises, failed_pairs is incremented."""
        evses = [_make_evse(1), _make_evse(2)]
        sim = _make_sim("CP-1", "loc-1", evses)
        sim._ocpp_client.start_transaction = AsyncMock(side_effect=RuntimeError("CSMS rejected"))
        vehicles = [_make_vehicle("tag-1"), _make_vehicle("tag-2")]
        charger_rows = [_make_row("CP-1")]

        no_sleep = AsyncMock()

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            run = await run_rush_period("loc-1", 2, charger_rows, vehicles, sleep_fn=no_sleep)

        assert run.status == "completed"
        assert run.failed_pairs == 2
        assert run.completed_pairs == 0


# ---------------------------------------------------------------------------
# Tests: cancellation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRushPeriodCancellation:
    async def test_cancellation_halts_further_plug_ins(self):
        """Setting status to 'cancelled' mid-loop stops further plug-ins."""
        evses = [_make_evse(i) for i in range(1, 4)]
        sim = _make_sim("CP-1", "loc-1", evses)
        vehicles = [_make_vehicle(f"tag-{i}") for i in range(1, 4)]
        charger_rows = [_make_row("CP-1")]

        plug_in_count = 0

        async def cancel_after_first(connector_id, id_tag, **kwargs) -> int:
            nonlocal plug_in_count
            plug_in_count += 1
            # Cancel the scenario after the first plug-in
            run = get_active_scenario("loc-1")
            if run:
                run.status = "cancelled"
            return 1

        sim._ocpp_client.start_transaction = cancel_after_first

        async def fake_sleep(secs: float) -> None:
            pass  # don't actually wait

        with patch("simulator_core.scenario_engine.store") as mock_store:
            mock_store.get_all.return_value = [sim]
            run = await run_rush_period("loc-1", 3, charger_rows, vehicles, sleep_fn=fake_sleep)

        # Only the first plug-in should have completed before cancellation
        assert plug_in_count == 1


# ---------------------------------------------------------------------------
# Tests: in-memory store helpers
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestScenarioStore:
    def test_set_and_get(self):
        from datetime import datetime, timezone
        run = ScenarioRun(
            location_id="loc-x",
            scenario_type="rush_period",
            duration_minutes=5,
            started_at=datetime.now(timezone.utc),
            total_pairs=3,
        )
        set_active_scenario("loc-x", run)
        assert get_active_scenario("loc-x") is run

    def test_clear_removes_scenario(self):
        from datetime import datetime, timezone
        run = ScenarioRun(
            location_id="loc-x",
            scenario_type="rush_period",
            duration_minutes=5,
            started_at=datetime.now(timezone.utc),
            total_pairs=1,
        )
        set_active_scenario("loc-x", run)
        clear_scenario("loc-x")
        assert get_active_scenario("loc-x") is None

    def test_get_returns_none_when_absent(self):
        assert get_active_scenario("nonexistent") is None
