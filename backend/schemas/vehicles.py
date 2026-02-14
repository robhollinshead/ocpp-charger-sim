"""Pydantic schemas for vehicle API."""
from pydantic import BaseModel, Field


class VehicleCreate(BaseModel):
    """Payload for creating a vehicle."""

    name: str = Field(..., min_length=1)
    idTags: list[str] = Field(..., min_length=1)
    battery_capacity_kWh: float = Field(..., gt=0)


class VehicleResponse(BaseModel):
    """Vehicle in list/detail responses."""

    id: str
    name: str
    idTags: list[str]
    battery_capacity_kWh: float
    location_id: str
