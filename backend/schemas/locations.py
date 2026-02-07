"""Pydantic schemas for location API."""
from pydantic import BaseModel


class LocationCreate(BaseModel):
    """Payload for creating a location."""

    name: str
    address: str


class LocationResponse(BaseModel):
    """Location in API responses."""

    id: str
    name: str
    address: str
    charger_count: int = 0
