"""Pydantic schemas for scenario requests and responses."""
from pydantic import BaseModel, Field


class RushPeriodConfig(BaseModel):
    duration_minutes: int = Field(ge=1, le=480, description="Window in minutes over which plug-ins are spread")


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
