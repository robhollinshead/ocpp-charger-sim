"""OCPP 1.6 Charging Profile data model, evaluation engine, and JSON persistence."""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

LOG = logging.getLogger(__name__)

_PROFILES_DIR_ENV = "PROFILES_DIR"
_SECONDS_PER_DAY = 86400
_SECONDS_PER_WEEK = 86400 * 7

# AC grid constants (matching evse.py)
_AC_GRID_VOLTAGE_V = 400.0
_SQRT3 = math.sqrt(3)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ChargingSchedulePeriod:
    """A single period entry in a ChargingSchedule."""
    start_period_s: int          # seconds from schedule start
    limit_W: float               # always stored in Watts (normalised at ingest)
    raw_limit: float             # original value from CSMS (A or W)
    raw_unit: str                # "A" or "W"
    number_phases: Optional[int] = None


@dataclass
class ChargingProfile:
    """Full OCPP 1.6 ChargingProfile structure."""
    charging_profile_id: int
    connector_id: int            # 0 = applies to the whole charge point
    stack_level: int
    charging_profile_purpose: str   # TxProfile | TxDefaultProfile | ChargePointMaxProfile
    charging_profile_kind: str      # Absolute | Recurring | Relative
    recurrency_kind: Optional[str] = None    # Daily | Weekly (Recurring only)
    transaction_id: Optional[int] = None     # Required for TxProfile
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    start_schedule: Optional[datetime] = None
    duration_s: Optional[int] = None
    charging_schedule_periods: list[ChargingSchedulePeriod] = field(default_factory=list)
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EvaluationResult:
    """Result of evaluating charging profiles for a connector at a point in time."""
    limit_W: float
    profile_id: int
    purpose: str
    stack_level: int
    period_index: int
    capped_by_max_profile: bool = False


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------

def normalize_limit_to_W(limit: float, unit: str, power_type: str) -> float:
    """Convert a charging limit to Watts.

    unit: "A" or "W"
    power_type: "AC" or "DC"
    """
    if unit.upper() == "W":
        return limit
    # Amperes → Watts
    if power_type == "AC":
        return limit * _SQRT3 * _AC_GRID_VOLTAGE_V
    else:
        from simulator_core.dc_voltage import get_pack_voltage_V
        return limit * get_pack_voltage_V(50.0)


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

def _parse_dt(value: object) -> Optional[datetime]:
    """Parse an ISO 8601 string or datetime to a timezone-aware datetime, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _start_of_day_utc(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_week_utc(now: datetime) -> datetime:
    day = _start_of_day_utc(now)
    return day - timedelta(days=day.weekday())


def _compute_elapsed(
    profile: ChargingProfile,
    now: datetime,
    tx_start_time: Optional[datetime],
) -> Optional[float]:
    """Compute elapsed seconds into the profile's schedule.

    Returns None if the profile is not yet applicable
    (Relative kind with no transaction start time).
    """
    kind = profile.charging_profile_kind
    if kind == "Absolute":
        base = profile.start_schedule or profile.received_at
        return max(0.0, (now - base).total_seconds())
    elif kind == "Recurring":
        recurrency = (profile.recurrency_kind or "Daily").upper()
        if recurrency == "WEEKLY":
            base = profile.start_schedule or _start_of_week_utc(now)
            period = _SECONDS_PER_WEEK
        else:  # Daily (default)
            base = profile.start_schedule or _start_of_day_utc(now)
            period = _SECONDS_PER_DAY
        return (now - base).total_seconds() % period
    else:  # Relative
        if tx_start_time is None:
            return None
        return max(0.0, (now - tx_start_time).total_seconds())


def _resolve_period(
    periods: list[ChargingSchedulePeriod],
    elapsed: float,
) -> tuple[int, float]:
    """Return (period_index, limit_W) for the active period.

    Active period = highest start_period_s ≤ elapsed.
    If elapsed is before all periods, use the first period.
    """
    if not periods:
        return 0, 0.0
    active = [(i, p) for i, p in enumerate(periods) if p.start_period_s <= elapsed]
    if not active:
        return 0, periods[0].limit_W
    idx, period = max(active, key=lambda x: x[1].start_period_s)
    return idx, period.limit_W


def _highest_stack(profiles: list[ChargingProfile]) -> Optional[ChargingProfile]:
    """Return the profile with the highest stack_level; ties broken by most-recent received_at."""
    if not profiles:
        return None
    return max(profiles, key=lambda p: (p.stack_level, p.received_at))


# ---------------------------------------------------------------------------
# Core evaluator
# ---------------------------------------------------------------------------

def evaluate_profiles(
    profiles: list[ChargingProfile],
    now: datetime,
    connector_id: int,
    transaction_id: Optional[int],
    tx_start_time: Optional[datetime],
) -> Optional[EvaluationResult]:
    """Evaluate OCPP 1.6 charging profiles for a connector.

    Returns EvaluationResult with the effective limit in Watts, or None when
    no valid profile applies.  None means the charger should not deliver power
    (the caller is responsible for transitioning to SuspendedEVSE).

    Priority: TxProfile (transaction-specific) > TxDefaultProfile.
    ChargePointMaxProfile (connector_id == 0) caps the result.
    Connector isolation: profiles on connector N do not affect connector M.
    """
    # Step 1: Filter by connector applicability
    applicable = [
        p for p in profiles
        if p.connector_id == connector_id or p.connector_id == 0
    ]

    # Step 2: Filter by validity window
    applicable = [
        p for p in applicable
        if (p.valid_from is None or p.valid_from <= now)
        and (p.valid_to is None or now < p.valid_to)
    ]

    # Step 3: Separate by purpose
    tx_profiles = [p for p in applicable if p.charging_profile_purpose == "TxProfile"]
    tx_default_profiles = [p for p in applicable if p.charging_profile_purpose == "TxDefaultProfile"]
    max_profiles = [p for p in applicable if p.charging_profile_purpose == "ChargePointMaxProfile"]

    # Step 4: TxProfile only applies during an active transaction with matching transaction_id
    if transaction_id is not None:
        tx_profiles = [
            p for p in tx_profiles
            if p.transaction_id is None or p.transaction_id == transaction_id
        ]
    else:
        tx_profiles = []  # TxProfile never applies outside a transaction

    # Step 5: Pick best (TxProfile wins over TxDefaultProfile)
    best = _highest_stack(tx_profiles) or _highest_stack(tx_default_profiles)
    if best is None:
        return None  # No applicable limit profile

    # Step 6: Compute elapsed time; check if profile is applicable yet
    elapsed = _compute_elapsed(best, now, tx_start_time)
    if elapsed is None:
        return None  # Relative profile with no transaction start time

    # Step 7: Check if duration has been exceeded
    if best.duration_s is not None and elapsed > best.duration_s:
        return None  # Profile has expired

    # Step 8: Resolve the active schedule period
    period_idx, limit_W = _resolve_period(best.charging_schedule_periods, elapsed)

    # Step 9: Apply ChargePointMaxProfile cap
    capped = False
    max_best = _highest_stack(max_profiles)
    if max_best is not None:
        max_elapsed = _compute_elapsed(max_best, now, tx_start_time)
        if max_elapsed is not None:
            if max_best.duration_s is None or max_elapsed <= max_best.duration_s:
                _, max_limit_W = _resolve_period(max_best.charging_schedule_periods, max_elapsed)
                if limit_W > max_limit_W:
                    limit_W = max_limit_W
                    capped = True

    return EvaluationResult(
        limit_W=limit_W,
        profile_id=best.charging_profile_id,
        purpose=best.charging_profile_purpose,
        stack_level=best.stack_level,
        period_index=period_idx,
        capped_by_max_profile=capped,
    )


def profile_matches_clear(
    profile: ChargingProfile,
    profile_id: Optional[int],
    connector_id: Optional[int],
    purpose: Optional[str],
    stack_level: Optional[int],
) -> bool:
    """Return True if the profile matches ALL provided (non-None) clear criteria.

    A ClearChargingProfile with no criteria (all None) matches all profiles.
    """
    if profile_id is not None and profile.charging_profile_id != profile_id:
        return False
    if connector_id is not None and profile.connector_id != connector_id:
        return False
    if purpose is not None and profile.charging_profile_purpose != purpose:
        return False
    if stack_level is not None and profile.stack_level != stack_level:
        return False
    return True


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _profiles_dir() -> str:
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.environ.get(_PROFILES_DIR_ENV, os.path.join(backend_root, "data", "profiles"))


def _profile_to_dict(p: ChargingProfile) -> dict:
    return {
        "charging_profile_id": p.charging_profile_id,
        "connector_id": p.connector_id,
        "stack_level": p.stack_level,
        "charging_profile_purpose": p.charging_profile_purpose,
        "charging_profile_kind": p.charging_profile_kind,
        "recurrency_kind": p.recurrency_kind,
        "transaction_id": p.transaction_id,
        "valid_from": p.valid_from.isoformat() if p.valid_from else None,
        "valid_to": p.valid_to.isoformat() if p.valid_to else None,
        "start_schedule": p.start_schedule.isoformat() if p.start_schedule else None,
        "duration_s": p.duration_s,
        "received_at": p.received_at.isoformat(),
        "charging_schedule_periods": [
            {
                "start_period_s": sp.start_period_s,
                "limit_W": sp.limit_W,
                "raw_limit": sp.raw_limit,
                "raw_unit": sp.raw_unit,
                "number_phases": sp.number_phases,
            }
            for sp in p.charging_schedule_periods
        ],
    }


def _dict_to_profile(d: dict) -> ChargingProfile:
    periods = [
        ChargingSchedulePeriod(
            start_period_s=int(sp["start_period_s"]),
            limit_W=float(sp["limit_W"]),
            raw_limit=float(sp["raw_limit"]),
            raw_unit=str(sp["raw_unit"]),
            number_phases=sp.get("number_phases"),
        )
        for sp in d.get("charging_schedule_periods", [])
    ]
    return ChargingProfile(
        charging_profile_id=int(d["charging_profile_id"]),
        connector_id=int(d["connector_id"]),
        stack_level=int(d["stack_level"]),
        charging_profile_purpose=str(d["charging_profile_purpose"]),
        charging_profile_kind=str(d["charging_profile_kind"]),
        recurrency_kind=d.get("recurrency_kind"),
        transaction_id=d.get("transaction_id"),
        valid_from=_parse_dt(d.get("valid_from")),
        valid_to=_parse_dt(d.get("valid_to")),
        start_schedule=_parse_dt(d.get("start_schedule")),
        duration_s=d.get("duration_s"),
        charging_schedule_periods=periods,
        received_at=_parse_dt(d.get("received_at")) or datetime.now(timezone.utc),
    )


def save_profiles(charge_point_id: str, profiles: list[ChargingProfile]) -> None:
    """Persist profiles to JSON. Creates directory if needed. Logs and swallows on failure."""
    try:
        d = _profiles_dir()
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{charge_point_id}.json")
        data = [_profile_to_dict(p) for p in profiles]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        LOG.warning("Failed to save profiles for %s: %s", charge_point_id, e)


def load_profiles(charge_point_id: str) -> list[ChargingProfile]:
    """Load profiles from JSON. Returns empty list if file missing or corrupt."""
    try:
        path = os.path.join(_profiles_dir(), f"{charge_point_id}.json")
        if not os.path.exists(path):
            return []
        with open(path) as f:
            data = json.load(f)
        return [_dict_to_profile(d) for d in data]
    except Exception as e:
        LOG.warning("Failed to load profiles for %s: %s", charge_point_id, e)
        return []
