"""Pydantic schemas for Charging Profile API responses."""
from typing import Optional

from pydantic import BaseModel


class ChargingSchedulePeriodResponse(BaseModel):
    start_period_s: int
    limit_W: float
    raw_limit: float
    raw_unit: str
    number_phases: Optional[int] = None


class ChargingProfileResponse(BaseModel):
    charging_profile_id: int
    connector_id: int
    stack_level: int
    charging_profile_purpose: str
    charging_profile_kind: str
    recurrency_kind: Optional[str] = None
    transaction_id: Optional[int] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    start_schedule: Optional[str] = None
    duration_s: Optional[int] = None
    charging_schedule_periods: list[ChargingSchedulePeriodResponse]
    received_at: str
    # Derived display fields
    status: str          # "Active" | "Scheduled" | "Expired"
    current_limit_W: Optional[float] = None   # evaluated right now (None if not Active)


class EvaluatedLimitResponse(BaseModel):
    connector_id: int
    transaction_id: Optional[int] = None
    limit_W: Optional[float] = None       # None = no profile active
    effective_W: float                     # always a number (0.0 when no profile)
    profile_id: Optional[int] = None
    purpose: Optional[str] = None
    stack_level: Optional[int] = None
    capped_by_max_profile: bool = False
