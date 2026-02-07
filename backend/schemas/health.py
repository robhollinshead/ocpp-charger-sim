"""Health check response schema."""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str = "ok"
    service: str = "ocpp-simulator"
