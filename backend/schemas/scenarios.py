"""Pydantic schemas for scenario requests and responses."""
from pydantic import BaseModel, Field


class RushPeriodConfig(BaseModel):
    duration_minutes: int = Field(ge=1, le=480, description="Window in minutes over which plug-ins are spread")
    num_vehicles: int | None = Field(default=None, ge=1, description="Max vehicle-EVSE pairs to schedule; None = all available")
    start_soc_midpoint_pct: float = Field(default=20.0, ge=0, le=100, description="Midpoint of randomised starting SoC window (±5%, clamped 0–100)")


class ScenarioRunResponse(BaseModel):
    location_id: str
    scenario_type: str
    duration_minutes: int
    started_at: str
    total_pairs: int
    completed_pairs: int
    failed_pairs: int
    offline_charger_ids: list[str]
    status: str  # "running" | "completed" | "cancelled"


class StopAllChargingResponse(BaseModel):
    stopped: int
    errors: int
