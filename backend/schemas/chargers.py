"""Pydantic schemas for charger API."""
from pydantic import BaseModel, Field


class ChargerCreate(BaseModel):
    """Payload for creating a charger."""

    connection_url: str
    charge_point_id: str
    charger_name: str
    ocpp_version: str = Field(default="1.6")
    evse_count: int = Field(default=1, ge=1, le=10)


class ChargerUpdate(BaseModel):
    """Payload for updating a charger (all fields optional)."""

    connection_url: str | None = None
    charger_name: str | None = None
    ocpp_version: str | None = None


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
    evses: list[EvseStatus]
    config: dict = {}
    connected: bool = False


class OCPPLogEntry(BaseModel):
    """Single OCPP message log entry (session-scoped)."""

    id: str
    timestamp: str
    direction: str  # 'incoming' | 'outgoing'
    messageType: str
    payload: str
    status: str = "success"
