"""Charger model: identity, EVSEs, config, optional OCPP connection."""
import asyncio
import logging
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

LOG = logging.getLogger(__name__)

from schemas.chargers import DEFAULT_METER_MEASURANDS_AC, DEFAULT_METER_MEASURANDS_DC
from simulator_core.evse import EVSE


class ConnectivityMode(str, Enum):
    """Charger connectivity mode: ONLINE (normal) or OFFLINE (forced, cache messages)."""
    ONLINE = "online"
    OFFLINE = "offline"


@dataclass
class CachedMessage:
    """An OCPP message cached during offline operation for replay on reconnect."""
    message_type: str           # "StatusNotification" | "StartTransaction" | "StopTransaction" | "MeterValues"
    payload: Any                # ocpp call.XxxPayload object
    connector_id: int           # which EVSE connector
    local_transaction_id: Optional[int]  # negative if offline-started tx, None for online-started tx
    timestamp: str              # ISO 8601 UTC timestamp when cached

_DEFAULT_MEASURANDS_DC = DEFAULT_METER_MEASURANDS_DC.split(",")
_DEFAULT_MEASURANDS_AC = DEFAULT_METER_MEASURANDS_AC.split(",")

# Maximum cached messages per charger (guards against unbounded growth during long offline periods).
# At the default 30s interval, this covers ~1 hour of meter data for a single active transaction.
_MAX_CACHE_SIZE = 120


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
        "_connectivity_mode",
        "_online_event",
        "_message_cache",
        "_offline_tx_counter",
        "_meter_tasks",
        "_charging_profiles",
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
        self._connectivity_mode: ConnectivityMode = ConnectivityMode.ONLINE
        self._online_event: asyncio.Event = asyncio.Event()
        self._online_event.set()  # starts in online state
        self._message_cache: deque[CachedMessage] = deque(maxlen=_MAX_CACHE_SIZE)  # Bounded FIFO queue; oldest dropped if full
        self._offline_tx_counter: int = 0  # Counts down: 0, -1, -2, ... for offline transaction IDs
        self._meter_tasks: dict[int, Any] = {}  # connector_id -> (task, stop_event); lives on Charger so it survives reconnects
        self._charging_profiles: list[Any] = []  # list[ChargingProfile]; populated by profile store on startup
        # Propagate power_type and TxDefaultPowerW to EVSEs
        tx_default_w = self.get_tx_default_power_w()
        for evse in self.evses:
            evse.power_type = power_type
            evse.tx_default_power_W = tx_default_w

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

    def get_meter_measurands(self) -> list[str]:
        """Return configured MeterValuesSampledData as a list of tokens, with power-type default."""
        val = self.config.get("MeterValuesSampledData")
        if val:
            return [m.strip() for m in str(val).split(",") if m.strip()]
        return _DEFAULT_MEASURANDS_DC if self.power_type == "DC" else _DEFAULT_MEASURANDS_AC

    def get_heartbeat_interval_s(self) -> int:
        """Heartbeat interval in seconds (default 120s)."""
        return int(self.config.get("HeartbeatInterval", 120))

    def is_ocpp_authorization_enabled(self) -> bool:
        """True if charger should send Authorize to CSMS before StartTransaction (default True)."""
        return bool(self.config.get("OCPPAuthorizationEnabled", True))

    # --------------- Offline / connectivity mode ---------------

    def is_offline_mode(self) -> bool:
        """True when charger is in forced offline mode (WS closed, messages cached)."""
        return self._connectivity_mode == ConnectivityMode.OFFLINE

    def set_offline(self) -> None:
        """Enter forced offline mode. Does NOT set _stop_connect — connect loop stays alive."""
        self._connectivity_mode = ConnectivityMode.OFFLINE
        self._online_event.clear()

    def set_online(self) -> None:
        """Exit forced offline mode and allow the connect loop to reconnect."""
        self._connectivity_mode = ConnectivityMode.ONLINE
        self._online_event.set()

    async def wait_for_online(self) -> None:
        """Suspend the caller until set_online() is called (used by the connect loop)."""
        await self._online_event.wait()

    def get_tx_default_power_w(self) -> float:
        """Fallback charging power (W) when no SetChargingProfile has been received (default 7400 W)."""
        return float(self.config.get("TxDefaultPowerW", 7400.0))

    # --------------- Offline message cache ---------------

    def next_offline_transaction_id(self) -> int:
        """Generate a local transaction ID for offline-started sessions (-1, -2, ...)."""
        self._offline_tx_counter -= 1
        return self._offline_tx_counter

    def cache_message(self, msg: "CachedMessage") -> None:
        """Append an OCPP message to the offline cache (bounded FIFO; oldest dropped when full)."""
        if len(self._message_cache) == _MAX_CACHE_SIZE:
            LOG.warning(
                "Charger %s offline cache full (%d); dropping oldest message",
                self.charge_point_id, _MAX_CACHE_SIZE,
            )
        self._message_cache.append(msg)

    def pop_message_cache(self) -> list["CachedMessage"]:
        """Drain and return all cached messages; clears the cache."""
        msgs = list(self._message_cache)
        self._message_cache.clear()
        return msgs

    def get_message_cache(self) -> list["CachedMessage"]:
        """Return a snapshot of cached messages without clearing."""
        return list(self._message_cache)

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

    def get_limit_W(self, connector_id: int) -> Optional[float]:
        """Evaluate charging profiles for the given connector and return the limit in Watts.

        Returns None when no valid profile applies — the caller should treat this as
        'no power / transition to SuspendedEVSE'.
        """
        from simulator_core.charging_profile import evaluate_profiles
        now = datetime.now(timezone.utc)
        evse = self.get_evse(connector_id)
        tx_id = evse.transaction_id if evse is not None else None
        tx_start: Optional[datetime] = None
        if evse is not None and evse.session_start_time is not None:
            try:
                tx_start = datetime.fromisoformat(
                    evse.session_start_time.replace("Z", "+00:00")
                )
            except ValueError:
                pass
        result = evaluate_profiles(self._charging_profiles, now, connector_id, tx_id, tx_start)
        return result.limit_W if result is not None else None
