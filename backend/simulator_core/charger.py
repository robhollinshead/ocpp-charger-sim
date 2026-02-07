"""Charger model: identity, EVSEs, config, optional OCPP connection."""
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

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
        "_ocpp_client",
        "_stop_connect",
        "_ocpp_log",
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
    ) -> None:
        self.charge_point_id = charge_point_id
        self.evses = list(evses) if evses else []
        self.csms_url = csms_url
        self.config = dict(config) if config else {}
        self.location_id = location_id
        self.charger_name = charger_name
        self.ocpp_version = ocpp_version
        self._ocpp_client: Any = None  # Optional running OCPP client
        self._stop_connect = False
        self._ocpp_log: list[dict[str, Any]] = []  # Session-scoped OCPP message log

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

    def get_meter_interval_s(self) -> float:
        """Configurable meter interval (default 10s)."""
        return float(self.config.get("meter_interval_s", 10.0))

    def get_voltage_V(self) -> float:
        """Default voltage for EVSEs (e.g. 230 AC, 400 DC)."""
        return float(self.config.get("voltage_V", 230.0))

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
