"""Unit tests for the charging profile evaluator — pure function, no I/O."""
from datetime import datetime, timedelta, timezone

import pytest

from simulator_core.charging_profile import (
    ChargingProfile,
    ChargingSchedulePeriod,
    EvaluationResult,
    evaluate_profiles,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc


def _now() -> datetime:
    return datetime.now(_UTC)


def _make_period(start_s: int, limit_W: float) -> ChargingSchedulePeriod:
    return ChargingSchedulePeriod(
        start_period_s=start_s,
        limit_W=limit_W,
        raw_limit=limit_W,
        raw_unit="W",
    )


def _absolute(
    profile_id: int = 1,
    connector_id: int = 1,
    stack_level: int = 0,
    purpose: str = "TxDefaultProfile",
    periods: list[ChargingSchedulePeriod] | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    duration_s: int | None = None,
    start_schedule: datetime | None = None,
    transaction_id: int | None = None,
) -> ChargingProfile:
    return ChargingProfile(
        charging_profile_id=profile_id,
        connector_id=connector_id,
        stack_level=stack_level,
        charging_profile_purpose=purpose,
        charging_profile_kind="Absolute",
        transaction_id=transaction_id,
        valid_from=valid_from,
        valid_to=valid_to,
        start_schedule=start_schedule,
        duration_s=duration_s,
        charging_schedule_periods=periods or [_make_period(0, 11000.0)],
        received_at=_now() - timedelta(hours=1),
    )


# ---------------------------------------------------------------------------
# Basic cases
# ---------------------------------------------------------------------------


def test_no_profiles_returns_none():
    assert evaluate_profiles([], _now(), 1, None, None) is None


def test_absolute_single_period_returns_limit():
    profiles = [_absolute(periods=[_make_period(0, 22000.0)])]
    result = evaluate_profiles(profiles, _now(), 1, None, None)
    assert result is not None
    assert result.limit_W == 22000.0


def test_absolute_multi_period_resolves_correct_period():
    """With elapsed=150s, should pick period starting at 100s (not 0s or 200s)."""
    now = _now()
    start = now - timedelta(seconds=150)
    periods = [
        _make_period(0, 10000.0),
        _make_period(100, 20000.0),
        _make_period(200, 30000.0),
    ]
    profile = _absolute(periods=periods, start_schedule=start)
    result = evaluate_profiles([profile], now, 1, None, None)
    assert result is not None
    assert result.limit_W == 20000.0
    assert result.period_index == 1


def test_before_first_period_uses_first_period():
    """Elapsed < first start_period_s → use first period."""
    now = _now()
    start = now - timedelta(seconds=5)
    periods = [
        _make_period(10, 5000.0),   # starts at 10s, but elapsed is only 5s
        _make_period(20, 10000.0),
    ]
    profile = _absolute(periods=periods, start_schedule=start)
    result = evaluate_profiles([profile], now, 1, None, None)
    assert result is not None
    assert result.limit_W == 5000.0
    assert result.period_index == 0


# ---------------------------------------------------------------------------
# TxProfile gating
# ---------------------------------------------------------------------------


def test_tx_profile_requires_transaction():
    """TxProfile should not apply when transaction_id is None."""
    profile = _absolute(purpose="TxProfile", transaction_id=None)
    result = evaluate_profiles([profile], _now(), 1, None, None)
    assert result is None


def test_tx_profile_with_transaction_applies():
    profile = _absolute(purpose="TxProfile", transaction_id=42)
    result = evaluate_profiles([profile], _now(), 1, 42, None)
    assert result is not None
    assert result.purpose == "TxProfile"


def test_tx_profile_filtered_by_transaction_id():
    """TxProfile with mismatched transaction_id is excluded."""
    profile = _absolute(purpose="TxProfile", transaction_id=99)
    result = evaluate_profiles([profile], _now(), 1, 42, None)
    assert result is None


def test_tx_profile_with_null_transaction_id_matches_any_tx():
    """TxProfile with transaction_id=None matches any active transaction."""
    profile = _absolute(purpose="TxProfile", transaction_id=None)
    # TxProfile without tx id on profile still needs an active transaction
    result = evaluate_profiles([profile], _now(), 1, 42, None)
    assert result is not None


# ---------------------------------------------------------------------------
# Stack level priority
# ---------------------------------------------------------------------------


def test_stack_level_priority_higher_wins():
    low = _absolute(profile_id=1, stack_level=0, periods=[_make_period(0, 5000.0)])
    high = _absolute(profile_id=2, stack_level=1, periods=[_make_period(0, 20000.0)])
    result = evaluate_profiles([low, high], _now(), 1, None, None)
    assert result is not None
    assert result.limit_W == 20000.0
    assert result.stack_level == 1


def test_stack_level_tie_broken_by_received_at():
    """Tie in stack_level → most recently received profile wins."""
    older = ChargingProfile(
        charging_profile_id=1, connector_id=1, stack_level=0,
        charging_profile_purpose="TxDefaultProfile",
        charging_profile_kind="Absolute",
        charging_schedule_periods=[_make_period(0, 5000.0)],
        received_at=_now() - timedelta(hours=2),
    )
    newer = ChargingProfile(
        charging_profile_id=2, connector_id=1, stack_level=0,
        charging_profile_purpose="TxDefaultProfile",
        charging_profile_kind="Absolute",
        charging_schedule_periods=[_make_period(0, 15000.0)],
        received_at=_now() - timedelta(minutes=5),
    )
    result = evaluate_profiles([older, newer], _now(), 1, None, None)
    assert result is not None
    assert result.limit_W == 15000.0


# ---------------------------------------------------------------------------
# Validity window
# ---------------------------------------------------------------------------


def test_valid_from_future_excluded():
    profile = _absolute(valid_from=_now() + timedelta(hours=1))
    assert evaluate_profiles([profile], _now(), 1, None, None) is None


def test_valid_from_past_included():
    profile = _absolute(valid_from=_now() - timedelta(hours=1))
    result = evaluate_profiles([profile], _now(), 1, None, None)
    assert result is not None


def test_valid_to_expired_excluded():
    profile = _absolute(valid_to=_now() - timedelta(seconds=1))
    assert evaluate_profiles([profile], _now(), 1, None, None) is None


def test_valid_to_future_included():
    profile = _absolute(valid_to=_now() + timedelta(hours=1))
    result = evaluate_profiles([profile], _now(), 1, None, None)
    assert result is not None


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------


def test_duration_expired_returns_none():
    now = _now()
    start = now - timedelta(seconds=200)
    profile = _absolute(start_schedule=start, duration_s=100)  # expired 100s ago
    assert evaluate_profiles([profile], now, 1, None, None) is None


def test_duration_not_yet_expired():
    now = _now()
    start = now - timedelta(seconds=50)
    profile = _absolute(start_schedule=start, duration_s=100)
    result = evaluate_profiles([profile], now, 1, None, None)
    assert result is not None


# ---------------------------------------------------------------------------
# ChargePointMaxProfile cap
# ---------------------------------------------------------------------------


def test_max_profile_caps_tx_profile():
    now = _now()
    tx_profile = _absolute(profile_id=1, purpose="TxProfile",
                            transaction_id=1, periods=[_make_period(0, 32000.0)])
    max_profile = ChargingProfile(
        charging_profile_id=2, connector_id=0, stack_level=0,
        charging_profile_purpose="ChargePointMaxProfile",
        charging_profile_kind="Absolute",
        charging_schedule_periods=[_make_period(0, 25000.0)],
        received_at=now,
    )
    result = evaluate_profiles([tx_profile, max_profile], now, 1, 1, None)
    assert result is not None
    assert result.limit_W == 25000.0
    assert result.capped_by_max_profile is True


def test_max_profile_caps_tx_default():
    now = _now()
    tx_default = _absolute(profile_id=1, purpose="TxDefaultProfile",
                            periods=[_make_period(0, 30000.0)])
    max_profile = ChargingProfile(
        charging_profile_id=2, connector_id=0, stack_level=0,
        charging_profile_purpose="ChargePointMaxProfile",
        charging_profile_kind="Absolute",
        charging_schedule_periods=[_make_period(0, 20000.0)],
        received_at=now,
    )
    result = evaluate_profiles([tx_default, max_profile], now, 1, None, None)
    assert result is not None
    assert result.limit_W == 20000.0
    assert result.capped_by_max_profile is True


def test_max_profile_does_not_cap_when_limit_is_lower():
    now = _now()
    tx_default = _absolute(periods=[_make_period(0, 10000.0)])
    max_profile = ChargingProfile(
        charging_profile_id=2, connector_id=0, stack_level=0,
        charging_profile_purpose="ChargePointMaxProfile",
        charging_profile_kind="Absolute",
        charging_schedule_periods=[_make_period(0, 25000.0)],
        received_at=now,
    )
    result = evaluate_profiles([tx_default, max_profile], now, 1, None, None)
    assert result is not None
    assert result.limit_W == 10000.0
    assert result.capped_by_max_profile is False


# ---------------------------------------------------------------------------
# Recurring profiles
# ---------------------------------------------------------------------------


def test_recurring_daily_wraps():
    """Elapsed should wrap at 86400s for a Daily recurring profile."""
    # Use a start_schedule so we control the wrap point exactly
    now = _now().replace(hour=12, minute=0, second=0, microsecond=0)
    # Base yesterday same time — makes elapsed = 86400, wraps to 0 → period at 0s
    base = now - timedelta(hours=36)  # 36h ago → elapsed = 36 * 3600 % 86400 = 43200
    profile = ChargingProfile(
        charging_profile_id=1, connector_id=1, stack_level=0,
        charging_profile_purpose="TxDefaultProfile",
        charging_profile_kind="Recurring",
        recurrency_kind="Daily",
        start_schedule=base,
        charging_schedule_periods=[
            _make_period(0, 5000.0),
            _make_period(43000, 15000.0),   # active from 43000s (≈12h elapsed)
        ],
        received_at=now,
    )
    result = evaluate_profiles([profile], now, 1, None, None)
    assert result is not None
    assert result.limit_W == 15000.0  # 43200 > 43000


def test_recurring_weekly_wraps():
    now = _now()
    # Start base 8 days ago → elapsed = 8 days % 7 days = 1 day = 86400s
    base = now - timedelta(days=8)
    profile = ChargingProfile(
        charging_profile_id=1, connector_id=1, stack_level=0,
        charging_profile_purpose="TxDefaultProfile",
        charging_profile_kind="Recurring",
        recurrency_kind="Weekly",
        start_schedule=base,
        charging_schedule_periods=[
            _make_period(0, 5000.0),
            _make_period(80000, 20000.0),   # active after 80000s (≈22h into the week)
        ],
        received_at=now,
    )
    result = evaluate_profiles([profile], now, 1, None, None)
    assert result is not None
    # elapsed = 8 days % 7 days = 86400s; 86400 > 80000 → 20000W
    assert result.limit_W == 20000.0


# ---------------------------------------------------------------------------
# Relative profiles
# ---------------------------------------------------------------------------


def test_relative_no_tx_start_returns_none():
    profile = ChargingProfile(
        charging_profile_id=1, connector_id=1, stack_level=0,
        charging_profile_purpose="TxProfile",
        charging_profile_kind="Relative",
        transaction_id=1,
        charging_schedule_periods=[_make_period(0, 7000.0)],
        received_at=_now(),
    )
    result = evaluate_profiles([profile], _now(), 1, 1, None)
    assert result is None


def test_relative_with_tx_start_resolves_period():
    now = _now()
    tx_start = now - timedelta(seconds=150)
    profile = ChargingProfile(
        charging_profile_id=1, connector_id=1, stack_level=0,
        charging_profile_purpose="TxProfile",
        charging_profile_kind="Relative",
        transaction_id=1,
        charging_schedule_periods=[
            _make_period(0, 5000.0),
            _make_period(100, 10000.0),
        ],
        received_at=now,
    )
    result = evaluate_profiles([profile], now, 1, 1, tx_start)
    assert result is not None
    assert result.limit_W == 10000.0


# ---------------------------------------------------------------------------
# Connector isolation
# ---------------------------------------------------------------------------


def test_connector_0_applies_to_any_connector():
    """Profile on connector 0 (ChargePointMaxProfile) applies to all connectors."""
    max_profile = ChargingProfile(
        charging_profile_id=1, connector_id=0, stack_level=0,
        charging_profile_purpose="ChargePointMaxProfile",
        charging_profile_kind="Absolute",
        charging_schedule_periods=[_make_period(0, 25000.0)],
        received_at=_now(),
    )
    tx_default_c1 = _absolute(profile_id=2, connector_id=1,
                               periods=[_make_period(0, 30000.0)])
    tx_default_c2 = _absolute(profile_id=3, connector_id=2,
                               periods=[_make_period(0, 28000.0)])

    result_c1 = evaluate_profiles([max_profile, tx_default_c1, tx_default_c2], _now(), 1, None, None)
    result_c2 = evaluate_profiles([max_profile, tx_default_c1, tx_default_c2], _now(), 2, None, None)

    assert result_c1 is not None and result_c1.limit_W == 25000.0
    assert result_c2 is not None and result_c2.limit_W == 25000.0


def test_connector_isolation_connectors_independent():
    """Profiles on connector 1 do not affect connector 2 evaluation."""
    c1_profile = _absolute(profile_id=1, connector_id=1,
                            stack_level=2, periods=[_make_period(0, 16000.0)])
    c2_profile = _absolute(profile_id=2, connector_id=2,
                            stack_level=1, periods=[_make_period(0, 32000.0)])

    result_c1 = evaluate_profiles([c1_profile, c2_profile], _now(), 1, None, None)
    result_c2 = evaluate_profiles([c1_profile, c2_profile], _now(), 2, None, None)

    # c1 should use its own profile (16kW at sl=2)
    assert result_c1 is not None and result_c1.limit_W == 16000.0
    assert result_c1.stack_level == 2
    # c2 should use its own profile (32kW at sl=1)
    assert result_c2 is not None and result_c2.limit_W == 32000.0
    assert result_c2.stack_level == 1


def test_tx_profile_on_one_connector_does_not_affect_other():
    """TxProfile on connector 1 does not touch connector 2, which still uses TxDefault."""
    tx_profile_c1 = _absolute(profile_id=1, connector_id=1, purpose="TxProfile",
                               transaction_id=10, periods=[_make_period(0, 10000.0)])
    tx_default_c2 = _absolute(profile_id=2, connector_id=2, purpose="TxDefaultProfile",
                               periods=[_make_period(0, 20000.0)])

    result_c2 = evaluate_profiles(
        [tx_profile_c1, tx_default_c2], _now(), 2, None, None
    )
    assert result_c2 is not None
    assert result_c2.limit_W == 20000.0
    assert result_c2.purpose == "TxDefaultProfile"
