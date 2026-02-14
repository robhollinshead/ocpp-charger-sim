"""Async OCPP 1.6 charge point client: Boot, Status, Authorize, Start/StopTransaction, MeterValues, SetChargingProfile, RemoteStartTransaction, RemoteStopTransaction."""
import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional

from ocpp.routing import on
from ocpp.v16 import ChargePoint, call, call_result, datatypes
from ocpp.v16.enums import (
    Action,
    AuthorizationStatus,
    ChargePointErrorCode,
    ChargePointStatus,
    ChargingProfileStatus,
    ConfigurationStatus,
    Measurand,
    Reason,
    RemoteStartStopStatus,
    UnitOfMeasure,
)

from simulator_core.charger import Charger
from simulator_core.config_sync import persist_charger_config
from simulator_core.evse import EVSE, EvseState
from simulator_core.meter_engine import start_metering_loop
from simulator_core.meter_engine import MeterValuesPayload as DictMeterPayload

if TYPE_CHECKING:
    pass

LOG = logging.getLogger(__name__)

# OCPP message type IDs: Call=2, CallResult=3, CallError=4
_CALL = 2
_CALL_RESULT = 3
_CALL_ERROR = 4


def _parse_ocpp_message_type(raw: str) -> str:
    """Extract message type (action name or CallResult/CallError) from raw JSON message."""
    try:
        arr = json.loads(raw)
        if not isinstance(arr, list) or len(arr) < 3:
            return "Unknown"
        msg_type_id = arr[0]
        if msg_type_id == _CALL:
            return str(arr[2]) if len(arr) > 2 else "Call"
        if msg_type_id == _CALL_RESULT:
            return "CallResult"
        if msg_type_id == _CALL_ERROR:
            return "CallError"
        return "Unknown"
    except (json.JSONDecodeError, TypeError):
        return "Unknown"


def _connection_is_open(conn: Any) -> bool:
    """True if the websockets connection is open. Library uses .state, not .open."""
    try:
        from websockets.protocol import State
        state = getattr(conn, "state", None)
        return state == State.OPEN if state is not None else False
    except Exception:
        return getattr(conn, "open", False)


class LoggingWebSocket:
    """Wraps a websocket and appends every send/recv to the charger's OCPP log."""

    __slots__ = ("_ws", "_log_append")

    def __init__(self, ws: Any, log_append: Callable[[str, str, str, str], None]) -> None:
        self._ws = ws
        self._log_append = log_append

    @property
    def open(self) -> bool:
        return _connection_is_open(self._ws)

    async def send(self, message: str) -> None:
        msg_type = _parse_ocpp_message_type(message)
        self._log_append("outgoing", msg_type, message, "success")
        LOG.info("OCPP outgoing (%d bytes): %s", len(message), repr(message))
        await self._ws.send(message)

    async def recv(self) -> str:
        message = await self._ws.recv()
        msg_type = _parse_ocpp_message_type(message)
        self._log_append("incoming", msg_type, message, "success")
        LOG.info("OCPP incoming (%d bytes): %s", len(message), repr(message))
        return message

    async def close(self, code: int = 1000, reason: str = "") -> None:
        await self._ws.close(code=code, reason=reason)


# Known OCPP config keys (align with DEFAULT_CHARGER_CONFIG + voltage_V).
_KNOWN_CONFIG_KEYS = frozenset({
    "HeartbeatInterval",
    "ConnectionTimeOut",
    "MeterValuesSampleInterval",
    "ClockAlignedDataInterval",
    "AuthorizeRemoteTxRequests",
    "LocalAuthListEnabled",
    "OCPPAuthorizationEnabled",
    "voltage_V",
})

# Keys that accept integer values.
_INT_CONFIG_KEYS = frozenset({
    "HeartbeatInterval",
    "ConnectionTimeOut",
    "MeterValuesSampleInterval",
    "ClockAlignedDataInterval",
})

# Keys that accept boolean values.
_BOOL_CONFIG_KEYS = frozenset({
    "AuthorizeRemoteTxRequests",
    "LocalAuthListEnabled",
    "OCPPAuthorizationEnabled",
})

# Map our EvseState to OCPP ChargePointStatus
_EVSE_STATE_TO_OCPP: dict[EvseState, ChargePointStatus] = {
    EvseState.Available: ChargePointStatus.available,
    EvseState.Preparing: ChargePointStatus.preparing,
    EvseState.Charging: ChargePointStatus.charging,
    EvseState.SuspendedEV: ChargePointStatus.suspended_ev,
    EvseState.SuspendedEVSE: ChargePointStatus.suspended_evse,
    EvseState.Finishing: ChargePointStatus.finishing,
    EvseState.Faulted: ChargePointStatus.faulted,
    EvseState.Unavailable: ChargePointStatus.unavailable,
}


def _measurand_from_str(s: str) -> Measurand:
    """Map measurand string to enum (e.g. 'Energy.Active.Import.Register')."""
    m = getattr(Measurand, s.replace(".", "_").lower(), None)
    return m if m is not None else Measurand.energy_active_import_register


def _unit_from_str(s: str) -> UnitOfMeasure:
    """Map unit string to enum (e.g. 'Wh' -> wh)."""
    u = getattr(UnitOfMeasure, s.lower().replace(" ", "_"), None)
    return u if u is not None else UnitOfMeasure.wh


def _dict_to_meter_values_payload(d: DictMeterPayload) -> call.MeterValuesPayload:
    """Convert our meter payload dict to ocpp.v16 call.MeterValuesPayload."""
    connector_id = d["connectorId"]
    transaction_id = d.get("transactionId")
    meter_value_list = []
    for mv in d["meterValue"]:
        ts = mv["timestamp"]
        sampled = []
        for sv in mv["sampledValue"]:
            kw: dict[str, Any] = {
                "value": sv["value"],
                "measurand": _measurand_from_str(sv["measurand"]) if isinstance(sv["measurand"], str) else sv["measurand"],
                "unit": _unit_from_str(sv["unit"]) if isinstance(sv["unit"], str) else sv["unit"],
            }
            if "location" in sv and sv["location"] is not None:
                kw["location"] = sv["location"]
            sampled.append(datatypes.SampledValue(**kw))
        meter_value_list.append(datatypes.MeterValue(timestamp=ts, sampled_value=sampled))
    return call.MeterValuesPayload(
        connector_id=connector_id,
        meter_value=meter_value_list,
        transaction_id=transaction_id,
    )


class SimulatorChargePoint(ChargePoint):
    """
    OCPP 1.6 charge point client: sends Boot/Status/StartTx/StopTx/MeterValues,
    handles Authorize, SetChargingProfile, RemoteStartTransaction, RemoteStopTransaction.
    """

    def __init__(self, charge_point_id: str, connection: Any, response_timeout: int = 30) -> None:
        super().__init__(charge_point_id, connection, response_timeout=response_timeout)
        self._charger: Optional[Charger] = None
        self._meter_tasks: dict[int, tuple[asyncio.Task, asyncio.Event]] = {}
        self._transaction_id_counter = 0

    def set_charger(self, charger: Charger) -> None:
        self._charger = charger

    def _next_transaction_id(self) -> int:
        self._transaction_id_counter += 1
        return self._transaction_id_counter

    async def send_boot_notification(self) -> call_result.BootNotificationPayload:
        """Send BootNotification on connect (vendor, model, firmware from charger)."""
        vendor = getattr(self._charger, "charge_point_vendor", None) or "FastCharge"
        model = getattr(self._charger, "charge_point_model", None) or "Pro 150"
        firmware = getattr(self._charger, "firmware_version", None) or "2.4.1"
        req = call.BootNotificationPayload(
            charge_point_vendor=vendor,
            charge_point_model=model,
            firmware_version=firmware,
        )
        return await self.call(req)

    async def send_status_notification(self, connector_id: int, status: EvseState) -> None:
        """Send StatusNotification for EVSE state change."""
        ocpp_status = _EVSE_STATE_TO_OCPP.get(status, ChargePointStatus.available)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        req = call.StatusNotificationPayload(
            connector_id=connector_id,
            error_code=ChargePointErrorCode.no_error,
            status=ocpp_status,
            timestamp=now,
        )
        await self.call(req)

    @on(Action.Authorize)
    async def on_authorize(self, id_tag: str, **kwargs: Any) -> call_result.AuthorizePayload:
        """Dummy: accept any idTag."""
        return call_result.AuthorizePayload(
            id_tag_info=datatypes.IdTagInfo(status=AuthorizationStatus.accepted),
        )

    @on(Action.GetConfiguration)
    async def on_get_configuration(self, key: Optional[list] = None, **kwargs: Any) -> call_result.GetConfigurationPayload:
        """Return requested or all known config keys; unknown requested keys in unknown_key."""
        if not self._charger:
            return call_result.GetConfigurationPayload(
                configuration_key=[], unknown_key=key or [],
            )
        config = self._charger.config
        requested = (key or []) if isinstance(key, list) else ([key] if key is not None else [])
        if not requested:
            # Return all known keys
            keys_to_return = [k for k in _KNOWN_CONFIG_KEYS if k in config]
            if not keys_to_return:
                keys_to_return = list(_KNOWN_CONFIG_KEYS)
        else:
            keys_to_return = [k for k in requested if k in _KNOWN_CONFIG_KEYS]
        unknown = [k for k in requested if k not in _KNOWN_CONFIG_KEYS]

        def to_str(val: Any) -> str:
            if isinstance(val, bool):
                return "true" if val else "false"
            return str(val)

        configuration_key = [
            datatypes.KeyValue(
                key=k,
                readonly=False,
                value=to_str(config.get(k)) if k in config else None,
            )
            for k in keys_to_return
        ]
        return call_result.GetConfigurationPayload(
            configuration_key=configuration_key,
            unknown_key=unknown,
        )

    @on(Action.ChangeConfiguration)
    async def on_change_configuration(self, key: str, value: str, **kwargs: Any) -> call_result.ChangeConfigurationPayload:
        """Validate key/value, update in-memory config, persist to DB, return status."""
        if not self._charger:
            return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.rejected)
        if key not in _KNOWN_CONFIG_KEYS:
            return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.not_supported)

        parsed: Any = None
        if key in _INT_CONFIG_KEYS:
            try:
                parsed = int(value)
            except (ValueError, TypeError):
                return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.rejected)
        elif key in _BOOL_CONFIG_KEYS:
            v = (value or "").strip().lower()
            if v in ("true", "1", "yes"):
                parsed = True
            elif v in ("false", "0", "no"):
                parsed = False
            else:
                return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.rejected)
        elif key == "voltage_V":
            try:
                parsed = float(value)
            except (ValueError, TypeError):
                return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.rejected)
        else:
            return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.not_supported)

        self._charger.config[key] = parsed
        charge_point_id = self._charger.charge_point_id
        try:
            await asyncio.to_thread(persist_charger_config, charge_point_id, {key: parsed})
        except Exception as e:
            LOG.warning("ChangeConfiguration: persist failed for %s: %s", charge_point_id, e)
        return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.accepted)

    @on(Action.SetChargingProfile)
    async def on_set_charging_profile(
        self,
        connector_id: int,
        cs_charging_profiles: dict,
        **kwargs: Any,
    ) -> call_result.SetChargingProfilePayload:
        """Extract power limit and apply to EVSE (FR-5)."""
        if not self._charger:
            return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.rejected)
        evse = self._charger.get_evse(connector_id)
        if not evse:
            return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.rejected)
        try:
            # cs_charging_profiles: dict with charging_schedule, charging_schedule_period
            schedule = cs_charging_profiles.get("charging_schedule") or cs_charging_profiles.get("chargingSchedule")
            if not schedule:
                return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.rejected)
            periods = schedule.get("charging_schedule_period") or schedule.get("chargingSchedulePeriod") or []
            if not periods:
                return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.rejected)
            first = periods[0]
            limit = float(first.get("limit", 0.0))
            unit = (schedule.get("charging_rate_unit") or schedule.get("chargingRateUnit") or "W").upper()
            if unit == "A":
                limit = limit * (evse.voltage_V or 230.0)
            evse.set_offered_limit_W(limit)
            return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.accepted)
        except (TypeError, KeyError, ValueError) as e:
            LOG.warning("SetChargingProfile parse error: %s", e)
            return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.rejected)

    @on(Action.RemoteStartTransaction)
    async def on_remote_start_transaction(
        self,
        id_tag: str,
        **kwargs: Any,
    ) -> call_result.RemoteStartTransactionPayload:
        """Handle RemoteStartTransaction from CSMS: start charging on target EVSE.

        We schedule start_transaction as a background task because the OCPP message loop
        is sequential: it cannot recv() the StartTransactionResponse while blocked in this
        handler. Returning immediately allows the loop to process the subsequent
        StartTransaction request/response.
        """
        connector_id = kwargs.get("connector_id") or kwargs.get("connectorId")
        if not self._charger:
            return call_result.RemoteStartTransactionPayload(status=RemoteStartStopStatus.rejected)
        evse: Optional[EVSE] = None
        if connector_id is not None:
            evse = self._charger.get_evse(int(connector_id))
        else:
            for e in self._charger.evses:
                if e.state == EvseState.Available and e.transaction_id is None:
                    evse = e
                    break
        if not evse or evse.transaction_id is not None:
            return call_result.RemoteStartTransactionPayload(status=RemoteStartStopStatus.rejected)
        connector_id = evse.evse_id
        asyncio.create_task(self.start_transaction(connector_id, id_tag))
        return call_result.RemoteStartTransactionPayload(status=RemoteStartStopStatus.accepted)

    @on(Action.RemoteStopTransaction)
    async def on_remote_stop_transaction(
        self,
        transaction_id: int,
        **kwargs: Any,
    ) -> call_result.RemoteStopTransactionPayload:
        """Handle RemoteStopTransaction from CSMS: stop charging, send StopTransaction.

        We schedule stop_transaction as a background task for the same reason as
        RemoteStartTransaction: the OCPP message loop cannot recv() the
        StopTransaction response while blocked in this handler.
        """
        if not self._charger:
            return call_result.RemoteStopTransactionPayload(status=RemoteStartStopStatus.rejected)
        evse = self._charger.get_evse_by_transaction_id(transaction_id)
        if not evse:
            return call_result.RemoteStopTransactionPayload(status=RemoteStartStopStatus.rejected)
        connector_id = evse.evse_id
        asyncio.create_task(self._stop_transaction_remote(connector_id))
        return call_result.RemoteStopTransactionPayload(status=RemoteStartStopStatus.accepted)

    async def _stop_transaction_remote(self, connector_id: int) -> None:
        """Background task: stop transaction with reason=remote (called from RemoteStopTransaction handler)."""
        await self.stop_transaction(connector_id, reason=Reason.remote)

    async def start_transaction(
        self,
        connector_id: int,
        id_tag: str,
        *,
        start_soc_pct: float | None = None,
        battery_capacity_kwh: float | None = None,
    ) -> Optional[int]:
        """
        Start charging session: Preparing, optionally Authorize, then StartTransaction.
        If OCPPAuthorizationEnabled: send Authorize first; only on Accepted proceed to StartTransaction.
        If FreeVend: go straight to StartTransaction. Returns transaction_id or None on failure.
        When start_soc_pct or battery_capacity_kwh is None, uses vehicle resolver (100 kWh, 20% if not found).
        """
        if not self._charger:
            return None
        evse = self._charger.get_evse(connector_id)
        if not evse or evse.transaction_id is not None:
            return None
        if not evse.transition_to(EvseState.Preparing):
            return None
        await self.send_status_notification(connector_id, EvseState.Preparing)

        if self._charger.is_ocpp_authorization_enabled():
            try:
                auth_req = call.AuthorizePayload(id_tag=id_tag)
                auth_resp: call_result.AuthorizePayload | None = await self.call(auth_req)
            except Exception as e:
                LOG.warning("Authorize call failed: %s", e)
                evse.transition_to(EvseState.Available)
                await self.send_status_notification(connector_id, EvseState.Available)
                return None
            if auth_resp is None:
                LOG.warning("Authorize returned CallError or empty response; treating as rejected")
                evse.transition_to(EvseState.Available)
                await self.send_status_notification(connector_id, EvseState.Available)
                return None
            id_tag_info = auth_resp.id_tag_info
            status_val = id_tag_info["status"] if isinstance(id_tag_info, dict) else id_tag_info.status
            auth_accepted = status_val == AuthorizationStatus.accepted or (
                isinstance(status_val, str) and status_val.lower() == "accepted"
            )
            if not auth_accepted:
                evse.transition_to(EvseState.Available)
                await self.send_status_notification(connector_id, EvseState.Available)
                return None

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        req = call.StartTransactionPayload(
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=int(evse.energy_Wh),
            timestamp=now,
        )
        try:
            resp: call_result.StartTransactionPayload | None = await self.call(req)
        except Exception as e:
            LOG.warning("StartTransaction call failed: %s", e)
            evse.transition_to(EvseState.Available)
            await self.send_status_notification(connector_id, EvseState.Available)
            return None
        if resp is None:
            LOG.warning("StartTransaction returned CallError or empty response; treating as rejected")
            evse.transition_to(EvseState.Available)
            await self.send_status_notification(connector_id, EvseState.Available)
            return None

        id_tag_info = resp.id_tag_info
        status_val = id_tag_info["status"] if isinstance(id_tag_info, dict) else id_tag_info.status
        accepted = (
            (status_val == AuthorizationStatus.accepted or (isinstance(status_val, str) and status_val.lower() == "accepted"))
            and resp.transaction_id > 0
        )
        if not accepted:
            evse.transition_to(EvseState.Available)
            await self.send_status_notification(connector_id, EvseState.Available)
            return None

        if start_soc_pct is None or battery_capacity_kwh is None:
            resolver = self._charger.get_vehicle_resolver() if self._charger else None
            result = (resolver or (lambda _: None))(id_tag) if resolver else None
            if start_soc_pct is None:
                start_soc_pct = result[1] if result else 20.0
            if battery_capacity_kwh is None:
                battery_capacity_kwh = result[0] if result else 100.0

        evse.start_transaction(
            resp.transaction_id,
            id_tag,
            start_soc_pct=start_soc_pct,
            battery_capacity_wh=battery_capacity_kwh,
        )
        if not evse.transition_to(EvseState.Charging):
            evse.end_transaction()
            evse.transition_to(EvseState.Available)
            await self.send_status_notification(connector_id, EvseState.Available)
            return None
        await self.send_status_notification(connector_id, EvseState.Charging)

        async def send_meter_values(payload: DictMeterPayload) -> None:
            ocpp_payload = _dict_to_meter_values_payload(payload)
            await self.call(ocpp_payload)

        interval_s = self._charger.get_meter_interval_s()
        task, stop_event = start_metering_loop(evse, send_meter_values, interval_s)
        self._meter_tasks[connector_id] = (task, stop_event)
        return resp.transaction_id

    async def stop_transaction(self, connector_id: int, reason: Reason = Reason.local) -> bool:
        """Stop charging: stop metering, send StopTransaction, transition EVSE to Available."""
        if not self._charger:
            return False
        evse = self._charger.get_evse(connector_id)
        if not evse or evse.transaction_id is None:
            return False

        task_stop = self._meter_tasks.pop(connector_id, None)
        if task_stop:
            task, stop_event = task_stop
            stop_event.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        transaction_id = evse.transaction_id
        evse.transition_to(EvseState.Finishing)
        await self.send_status_notification(connector_id, EvseState.Finishing)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        req = call.StopTransactionPayload(
            meter_stop=int(evse.energy_Wh),
            timestamp=now,
            transaction_id=transaction_id,
            reason=reason,
            id_tag=None,
        )
        await self.call(req)

        evse.end_transaction()
        evse.transition_to(EvseState.Available)
        await self.send_status_notification(connector_id, EvseState.Available)
        return True


def build_connection_url(connection_url: str, charge_point_id: str) -> str:
    """Build WebSocket URL: connection_url (normalized with trailing slash) + charge_point_id."""
    base = connection_url.rstrip("/")
    return f"{base}/{charge_point_id}"


async def connect_charge_point(
    charger: Charger, url: str, *, basic_auth_password: Optional[str] = None
) -> None:
    """
    Long-running connect loop: connect to CSMS at url with exponential backoff (no cap).
    On success: BootNotification, then StatusNotification for each EVSE, then message loop.
    When connection drops, retry unless charger.should_stop_connect() (set by Disconnect).
    If basic_auth_password is set, send Authorization: Basic base64(charge_point_id:password).
    """
    try:
        import websockets
    except ImportError:
        LOG.error("websockets package required for OCPP client")
        return

    additional_headers: Optional[dict[str, str]] = None
    if basic_auth_password is not None:
        credentials = base64.b64encode(
            f"{charger.charge_point_id}:{basic_auth_password}".encode()
        ).decode()
        additional_headers = {"Authorization": f"Basic {credentials}"}

    base_delay = 2.0
    max_delay = 60.0
    delay = base_delay
    attempt = 0

    while not charger.should_stop_connect():
        attempt += 1
        try:
            connect_kw: dict[str, Any] = {
                "subprotocols": ["ocpp1.6"],
                "ping_interval": 20,
                "ping_timeout": 10,
                "close_timeout": 5,
            }
            if additional_headers is not None:
                connect_kw["additional_headers"] = additional_headers
            ws = await websockets.connect(url, **connect_kw)
        except Exception as e:
            LOG.warning("Connect attempt %s failed: %s", attempt, e)
            if charger.should_stop_connect():
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
            continue

        def log_append(direction: str, message_type: str, payload: str, status: str = "success") -> None:
            charger.append_ocpp_log(direction, message_type, payload, status)

        ws_wrapped = LoggingWebSocket(ws, log_append)
        cp = SimulatorChargePoint(charger.charge_point_id, ws_wrapped)
        cp.set_charger(charger)
        charger.set_ocpp_client(cp)
        delay = base_delay  # reset backoff on successful connect

        async def boot_and_status() -> None:
            """Send BootNotification then StatusNotification per EVSE. Must run alongside cp.start() so responses can be received."""
            await cp.send_boot_notification()
            for evse in charger.evses:
                status = evse.state if evse.state else EvseState.Available
                await cp.send_status_notification(evse.evse_id, status)

        async def heartbeat_loop() -> None:
            """Send Heartbeat every HeartbeatInterval seconds until cancelled."""
            interval = charger.get_heartbeat_interval_s()
            while True:
                try:
                    await asyncio.sleep(interval)
                    req = call.HeartbeatPayload()
                    await cp.call(req)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    LOG.debug("Heartbeat error (connection may be closed): %s", e)
                    break

        try:
            await asyncio.gather(cp.start(), boot_and_status(), heartbeat_loop())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Normal WebSocket closure (e.g. user clicked Disconnect) raises with "1000 (OK)"
            if "1000" in str(e) and "OK" in str(e):
                LOG.debug("Connection closed normally: %s", e)
            else:
                LOG.warning("Message loop error: %s", e)
        finally:
            charger.clear_ocpp_client()

        if charger.should_stop_connect():
            break
        await asyncio.sleep(delay)
        delay = min(delay * 2, max_delay)
