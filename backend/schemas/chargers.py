"""Pydantic schemas for charger API."""
from typing import Literal

from pydantic import BaseModel, Field


# Default OCPP config (single source of truth for new and backfilled chargers).
DEFAULT_CHARGER_CONFIG: dict = {
    "HeartbeatInterval": 120,
    "ConnectionTimeOut": 60,
    "MeterValuesSampleInterval": 30,
    "ClockAlignedDataInterval": 900,
    "AuthorizeRemoteTxRequests": True,
    "LocalAuthListEnabled": True,
    "OCPPAuthorizationEnabled": True,
}


class ChargerCreate(BaseModel):
    """Payload for creating a charger."""

    connection_url: str
    charge_point_id: str
    charger_name: str
    ocpp_version: str = Field(default="1.6")
    evse_count: int = Field(default=1, ge=1, le=10)
    charge_point_vendor: str = Field(default="FastCharge")
    charge_point_model: str = Field(default="Pro 150")
    firmware_version: str = Field(default="2.4.1")


class ChargerUpdate(BaseModel):
    """Payload for updating a charger (all fields optional). Identity fields not editable."""

    connection_url: str | None = None
    charger_name: str | None = None
    ocpp_version: str | None = None
    security_profile: Literal["none", "basic"] | None = None
    basic_auth_password: str | None = None  # Write-only; never in response.


class ChargerConfigUpdate(BaseModel):
    """Payload for updating charger OCPP config (editable keys only)."""

    HeartbeatInterval: int | None = None
    ConnectionTimeOut: int | None = None
    MeterValuesSampleInterval: int | None = None
    ClockAlignedDataInterval: int | None = None
    AuthorizeRemoteTxRequests: bool | None = None
    LocalAuthListEnabled: bool | None = None
    OCPPAuthorizationEnabled: bool | None = None


class MeterSnapshot(BaseModel):
    """Current meter values for an EVSE."""

    energy_Wh: float = 0.0
    power_W: float = 0.0
    voltage_V: float = 0.0
    current_A: float = 0.0


class EvseStatus(BaseModel):
    """EVSE status in charger detail."""

    evse_id: int
    state: str
    transaction_id: int | None = None
    id_tag: str | None = None
    session_start_time: str | None = None
    meter: MeterSnapshot


class StartTransactionRequest(BaseModel):
    """Payload for starting a transaction."""

    connector_id: int
    id_tag: str


class StartTransactionResponse(BaseModel):
    """Response from starting a transaction."""

    transaction_id: int


class StopTransactionRequest(BaseModel):
    """Payload for stopping a transaction."""

    connector_id: int


class ChargerSummary(BaseModel):
    """Charger list item."""

    id: str
    charge_point_id: str
    connection_url: str
    charger_name: str
    ocpp_version: str
    location_id: str
    evse_count: int
    connected: bool = False


class ChargerDetail(BaseModel):
    """Charger detail with EVSEs and config."""

    id: str
    charge_point_id: str
    connection_url: str
    charger_name: str
    ocpp_version: str
    location_id: str
    charge_point_vendor: str = "FastCharge"
    charge_point_model: str = "Pro 150"
    firmware_version: str = "2.4.1"
    evses: list[EvseStatus]
    config: dict = {}
    connected: bool = False
    security_profile: Literal["none", "basic"] = "none"
    basic_auth_password_set: bool = False


class OCPPLogEntry(BaseModel):
    """Single OCPP message log entry (session-scoped)."""

    id: str
    timestamp: str
    direction: str  # 'incoming' | 'outgoing'
    messageType: str
    payload: str
    status: str = "success"
