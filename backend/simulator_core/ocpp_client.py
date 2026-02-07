"""Async OCPP 1.6 charge point client: Boot, Status, Authorize, Start/StopTransaction, MeterValues, SetChargingProfile."""
import asyncio
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
    Measurand,
    Reason,
    UnitOfMeasure,
)

from simulator_core.charger import Charger
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
        sampled = [
            datatypes.SampledValue(
                value=sv["value"],
                measurand=_measurand_from_str(sv["measurand"]) if isinstance(sv["measurand"], str) else sv["measurand"],
                unit=_unit_from_str(sv["unit"]) if isinstance(sv["unit"], str) else sv["unit"],
            )
            for sv in mv["sampledValue"]
        ]
        meter_value_list.append(datatypes.MeterValue(timestamp=ts, sampled_value=sampled))
    return call.MeterValuesPayload(
        connector_id=connector_id,
        meter_value=meter_value_list,
        transaction_id=transaction_id,
    )


class SimulatorChargePoint(ChargePoint):
    """
    OCPP 1.6 charge point client: sends Boot/Status/StartTx/StopTx/MeterValues,
    handles Authorize (dummy) and SetChargingProfile.
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
        """Send BootNotification on connect."""
        req = call.BootNotificationPayload(
            charge_point_vendor="ocpp-sim",
            charge_point_model="simulator",
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

    async def start_transaction(self, connector_id: int, id_tag: str) -> Optional[int]:
        """
        Start charging session: Preparing, send StartTransaction, await CSMS response.
        If Accepted: Charging + metering loop. If Invalid: back to Available.
        Returns transaction_id or None on failure.
        """
        if not self._charger:
            return None
        evse = self._charger.get_evse(connector_id)
        if not evse or evse.transaction_id is not None:
            return None
        if not evse.transition_to(EvseState.Preparing):
            return None
        await self.send_status_notification(connector_id, EvseState.Preparing)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        req = call.StartTransactionPayload(
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=int(evse.energy_Wh),
            timestamp=now,
        )
        try:
            resp: call_result.StartTransactionPayload = await self.call(req)
        except Exception as e:
            LOG.warning("StartTransaction call failed: %s", e)
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

        evse.start_transaction(resp.transaction_id, id_tag)
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


async def connect_charge_point(charger: Charger, url: str) -> None:
    """
    Long-running connect loop: connect to CSMS at url with exponential backoff (no cap).
    On success: BootNotification, then StatusNotification for each EVSE, then message loop.
    When connection drops, retry unless charger.should_stop_connect() (set by Disconnect).
    """
    try:
        import websockets
    except ImportError:
        LOG.error("websockets package required for OCPP client")
        return

    base_delay = 2.0
    max_delay = 60.0
    delay = base_delay
    attempt = 0

    while not charger.should_stop_connect():
        attempt += 1
        try:
            ws = await websockets.connect(
                url,
                subprotocols=["ocpp1.6"],
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            )
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

        try:
            await asyncio.gather(cp.start(), boot_and_status())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            LOG.warning("Message loop error: %s", e)
        finally:
            charger.clear_ocpp_client()

        if charger.should_stop_connect():
            break
        await asyncio.sleep(delay)
        delay = min(delay * 2, max_delay)
