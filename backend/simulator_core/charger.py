"""Charger model: identity, EVSEs, config, optional OCPP connection."""
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from simulator_core.evse import EVSE


class Charger:
    """
    Charge point: 1–N EVSEs, optional CSMS URL and config.
    May hold an optional running OCPP client when connected.
    """

    __slots__ = (
        "charge_point_id",
        "evses",
        "csms_url",
        "config",
        "location_id",
        "charger_name",
        "ocpp_version",
        "charge_point_vendor",
        "charge_point_model",
        "firmware_version",
        "power_type",
        "_ocpp_client",
        "_stop_connect",
        "_ocpp_log",
        "_vehicle_resolver",
    )

    def __init__(
        self,
        charge_point_id: str,
        evses: Optional[list[EVSE]] = None,
        csms_url: Optional[str] = None,
        config: Optional[dict[str, Any]] = None,
        location_id: Optional[str] = None,
        charger_name: Optional[str] = None,
        ocpp_version: str = "1.6",
        charge_point_vendor: str = "FastCharge",
        charge_point_model: str = "Pro 150",
        firmware_version: str = "2.4.1",
        power_type: str = "DC",
    ) -> None:
        self.charge_point_id = charge_point_id
        self.evses = list(evses) if evses else []
        self.csms_url = csms_url
        self.config = dict(config) if config else {}
        self.location_id = location_id
        self.charger_name = charger_name
        self.ocpp_version = ocpp_version
        self.charge_point_vendor = charge_point_vendor
        self.charge_point_model = charge_point_model
        self.firmware_version = firmware_version
        self.power_type = power_type
        self._ocpp_client: Any = None  # Optional running OCPP client
        self._stop_connect = False
        self._ocpp_log: list[dict[str, Any]] = []  # Session-scoped OCPP message log
        self._vehicle_resolver: Optional[Callable[[str], Optional[tuple[float, float]]]] = None
        # Propagate power_type to EVSEs
        for evse in self.evses:
            evse.power_type = power_type

    def set_vehicle_resolver(
        self, resolver: Optional[Callable[[str], Optional[tuple[float, float]]]]
    ) -> None:
        """Set resolver for id_tag -> (battery_capacity_kwh, start_soc_pct). None = use 100 kWh, 20%."""
        self._vehicle_resolver = resolver

    def get_vehicle_resolver(
        self,
    ) -> Optional[Callable[[str], Optional[tuple[float, float]]]]:
        """Return vehicle resolver or None."""
        return self._vehicle_resolver

    def set_stop_connect(self, stop: bool = True) -> None:
        """Set flag to stop the connect loop from retrying (used on Disconnect)."""
        self._stop_connect = stop

    def clear_stop_connect(self) -> None:
        """Clear stop flag so Connect can start the loop again."""
        self._stop_connect = False

    def should_stop_connect(self) -> bool:
        """True if connect loop should exit and not retry."""
        return self._stop_connect

    def append_ocpp_log(
        self,
        direction: str,
        message_type: str,
        payload: str,
        status: str = "success",
    ) -> None:
        """Append an OCPP message to the session log (incoming or outgoing)."""
        self._ocpp_log.append({
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "direction": direction,
            "messageType": message_type,
            "payload": payload,
            "status": status,
        })

    def get_ocpp_log(self) -> list[dict[str, Any]]:
        """Return a copy of the session OCPP log."""
        return list(self._ocpp_log)

    def clear_ocpp_log(self) -> None:
        """Clear the session OCPP log."""
        self._ocpp_log.clear()

    def get_evse(self, evse_id: int) -> Optional[EVSE]:
        """Return EVSE by connector id or None."""
        for evse in self.evses:
            if evse.evse_id == evse_id:
                return evse
        return None

    def get_evse_by_transaction_id(self, transaction_id: int) -> Optional[EVSE]:
        """Return EVSE with the given transaction_id or None."""
        for evse in self.evses:
            if evse.transaction_id == transaction_id:
                return evse
        return None

    def get_meter_interval_s(self) -> float:
        """MeterValues sample interval in seconds (default 30s)."""
        return float(self.config.get("MeterValuesSampleInterval", 30))

    def get_heartbeat_interval_s(self) -> int:
        """Heartbeat interval in seconds (default 120s)."""
        return int(self.config.get("HeartbeatInterval", 120))

    def is_ocpp_authorization_enabled(self) -> bool:
        """True if charger should send Authorize to CSMS before StartTransaction (default True)."""
        return bool(self.config.get("OCPPAuthorizationEnabled", True))

    @property
    def is_connected(self) -> bool:
        """True if OCPP client is running and WebSocket is open."""
        if self._ocpp_client is None:
            return False
        conn = getattr(self._ocpp_client, "_connection", None)
        return getattr(conn, "open", False) if conn else False

    def set_ocpp_client(self, client: Any) -> None:
        """Attach running OCPP client (internal use)."""
        self._ocpp_client = client

    def clear_ocpp_client(self) -> None:
        """Detach OCPP client after disconnect."""
        self._ocpp_client = None
