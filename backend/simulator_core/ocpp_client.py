"""Async OCPP 1.6 charge point client: Boot, Status, Authorize, Start/StopTransaction, MeterValues, SetChargingProfile, RemoteStartTransaction, RemoteStopTransaction."""
import asyncio
import base64
import json
import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional

from ocpp.routing import on
from ocpp.v16 import ChargePoint, call, call_result, datatypes
from websockets.exceptions import ConnectionClosed
from ocpp.v16.enums import (
    Action,
    AuthorizationStatus,
    ChargePointErrorCode,
    ChargePointStatus,
    ChargingProfileStatus,
    ClearChargingProfileStatus,
    ConfigurationStatus,
    Measurand,
    Phase,
    Reason,
    RemoteStartStopStatus,
    UnitOfMeasure,
)

from simulator_core.charger import Charger
from simulator_core.config_sync import persist_charger_config
from simulator_core.dc_voltage import get_pack_voltage_V
from simulator_core.evse import EVSE, EvseState, AC_GRID_VOLTAGE_V, SQRT3
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


# Known OCPP config keys (align with DEFAULT_CHARGER_CONFIG).
_KNOWN_CONFIG_KEYS = frozenset({
    "HeartbeatInterval",
    "ConnectionTimeOut",
    "MeterValuesSampleInterval",
    "ClockAlignedDataInterval",
    "AuthorizeRemoteTxRequests",
    "LocalAuthListEnabled",
    "OCPPAuthorizationEnabled",
    "MeterValuesSampledData",
    "TxDefaultPowerW",
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

# Keys that accept string values.
_STRING_CONFIG_KEYS = frozenset({"MeterValuesSampledData"})

# Keys that accept float values.
_FLOAT_CONFIG_KEYS = frozenset({"TxDefaultPowerW"})

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
            if "phase" in sv and sv["phase"] is not None:
                phase_str = sv["phase"]
                phase_key = phase_str.lower().replace("-", "_")
                kw["phase"] = getattr(Phase, phase_key, phase_str)
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
        # NOTE: _meter_tasks lives on Charger (not here) so tasks survive reconnects.
        self._transaction_id_counter = 0

    def set_charger(self, charger: Charger) -> None:
        self._charger = charger

    def _next_transaction_id(self) -> int:
        self._transaction_id_counter += 1
        return self._transaction_id_counter

    def _make_send_meter_values(
        self,
        evse: "EVSE",
        connector_id: int,
        charger: "Charger",
    ) -> "Callable[[DictMeterPayload], Any]":
        """Build the send_meter_values callback for the metering loop.

        Routes through charger._ocpp_client when online (so meter ticks always go via the
        currently-active CP, not a stale or ephemeral self). Falls back to self._send_or_cache
        when offline so ticks are cached for replay.
        """
        async def send_meter_values(payload: DictMeterPayload) -> None:
            ocpp_payload = _dict_to_meter_values_payload(payload)
            local_tx = evse.transaction_id if evse.transaction_id and evse.transaction_id < 0 else None
            if charger.is_offline_mode():
                await self._send_or_cache(ocpp_payload, connector_id=connector_id, local_tx_id=local_tx)
            else:
                active_cp = charger._ocpp_client
                if active_cp is not None:
                    await active_cp._send_or_cache(ocpp_payload, connector_id=connector_id, local_tx_id=local_tx)
                # else: transitioning between connections — skip this tick
        return send_meter_values

    async def _send_or_cache(
        self,
        payload: Any,
        *,
        connector_id: int = 0,
        local_tx_id: Optional[int] = None,
    ) -> Any:
        """Send an OCPP message if online; cache it if charger is in offline mode.

        When offline, a CachedMessage is appended to charger._message_cache and None is
        returned. When online, the message is sent via self.call() and the response returned.
        connector_id and local_tx_id are stored on the cache entry for replay reconciliation.
        """
        from simulator_core.charger import CachedMessage
        charger = self._charger
        if charger is not None and charger.is_offline_mode():
            msg_type = type(payload).__name__.replace("Payload", "")
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            charger.cache_message(CachedMessage(
                message_type=msg_type,
                payload=payload,
                connector_id=connector_id,
                local_transaction_id=local_tx_id,
                timestamp=now,
            ))
            return None
        return await self.call(payload)

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

    async def send_status_notification(
        self,
        connector_id: int,
        status: EvseState,
        *,
        error_code: Optional[ChargePointErrorCode] = None,
        info: Optional[str] = None,
        vendor_error_code: Optional[str] = None,
    ) -> None:
        """Send StatusNotification for EVSE state change.

        Args:
            connector_id: The connector/EVSE id.
            status: The new EVSE state.
            error_code: ChargePointErrorCode enum value; defaults to no_error.
            info: Optional free-text diagnostic info (for Faulted status).
            vendor_error_code: Optional vendor-specific error code string.
        """
        ocpp_status = _EVSE_STATE_TO_OCPP.get(status, ChargePointStatus.available)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        req = call.StatusNotificationPayload(
            connector_id=connector_id,
            error_code=error_code if error_code is not None else ChargePointErrorCode.no_error,
            status=ocpp_status,
            timestamp=now,
            info=info,
            vendor_error_code=vendor_error_code,
        )
        await self._send_or_cache(req, connector_id=connector_id)

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
        elif key in _FLOAT_CONFIG_KEYS:
            try:
                parsed = float(value)
            except (ValueError, TypeError):
                return call_result.ChangeConfigurationPayload(status=ConfigurationStatus.rejected)
            # Propagate TxDefaultPowerW to all EVSEs immediately
            if key == "TxDefaultPowerW":
                for evse in self._charger.evses:
                    evse.tx_default_power_W = parsed
        elif key in _STRING_CONFIG_KEYS:
            parsed = value
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
        """Store the full ChargingProfile and evaluate/apply limits.

        Profiles are stored per charger with full OCPP 1.6 structure.
        All period limits are normalised to Watts at ingest.
        Any SuspendedEVSE connectors that now have a valid profile are resumed.
        """
        from simulator_core.charging_profile import (
            ChargingProfile,
            ChargingSchedulePeriod,
            normalize_limit_to_W,
            save_profiles,
        )
        if not self._charger:
            return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.rejected)
        try:
            raw = cs_charging_profiles
            schedule = raw.get("charging_schedule") or raw.get("chargingSchedule") or {}
            periods_raw = (
                schedule.get("charging_schedule_period")
                or schedule.get("chargingSchedulePeriod")
                or []
            )
            if not periods_raw:
                return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.rejected)

            unit = (schedule.get("charging_rate_unit") or schedule.get("chargingRateUnit") or "W").upper()
            power_type = getattr(self._charger, "power_type", "DC")

            periods = [
                ChargingSchedulePeriod(
                    start_period_s=int(p.get("start_period") or p.get("startPeriod") or 0),
                    limit_W=normalize_limit_to_W(float(p.get("limit", 0)), unit, power_type),
                    raw_limit=float(p.get("limit", 0)),
                    raw_unit=unit,
                    number_phases=p.get("number_phases") or p.get("numberOfPhases"),
                )
                for p in periods_raw
            ]

            def _get(key_snake: str, key_camel: str) -> Any:
                return raw.get(key_snake) or raw.get(key_camel)

            def _parse_dt(s: Any) -> Optional[datetime]:
                if s is None:
                    return None
                try:
                    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
                    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    return None

            profile = ChargingProfile(
                charging_profile_id=int(_get("charging_profile_id", "chargingProfileId") or 0),
                connector_id=connector_id,
                stack_level=int(_get("stack_level", "stackLevel") or 0),
                charging_profile_purpose=str(_get("charging_profile_purpose", "chargingProfilePurpose") or "TxProfile"),
                charging_profile_kind=str(_get("charging_profile_kind", "chargingProfileKind") or "Absolute"),
                recurrency_kind=_get("recurrency_kind", "recurrencyKind"),
                transaction_id=_get("transaction_id", "transactionId"),
                valid_from=_parse_dt(_get("valid_from", "validFrom")),
                valid_to=_parse_dt(_get("valid_to", "validTo")),
                start_schedule=_parse_dt(
                    schedule.get("start_schedule") or schedule.get("startSchedule")
                ),
                duration_s=schedule.get("duration"),
                charging_schedule_periods=periods,
            )

            # Replace any existing profile with the same (id, connector_id)
            existing = [
                p for p in self._charger._charging_profiles
                if not (
                    p.charging_profile_id == profile.charging_profile_id
                    and p.connector_id == profile.connector_id
                )
            ]
            existing.append(profile)
            self._charger._charging_profiles = existing

            cp_id = self._charger.charge_point_id
            profiles_copy = list(existing)
            asyncio.create_task(asyncio.to_thread(save_profiles, cp_id, profiles_copy))

            # Resume any SuspendedEVSE connectors that now have a valid profile
            await self._resume_evse_if_profile_available(connector_id)
            if connector_id == 0:
                for evse in self._charger.evses:
                    await self._resume_evse_if_profile_available(evse.evse_id)

            return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.accepted)
        except Exception as e:
            LOG.warning("SetChargingProfile error: %s", e)
            return call_result.SetChargingProfilePayload(status=ChargingProfileStatus.rejected)

    @on(Action.ClearChargingProfile)
    async def on_clear_charging_profile(self, **kwargs: Any) -> call_result.ClearChargingProfilePayload:
        """Remove charging profiles matching the provided criteria.

        All criteria are optional; when all are None all profiles are removed.
        Returns accepted if any profiles were removed, unknown if none matched.
        """
        from simulator_core.charging_profile import profile_matches_clear, save_profiles

        if not self._charger:
            return call_result.ClearChargingProfilePayload(status=ClearChargingProfileStatus.unknown)

        def _kw(*keys):
            for k in keys:
                v = kwargs.get(k)
                if v is not None:
                    return v
            return None

        profile_id = _kw("id", "charging_profile_id")
        conn_id = _kw("connector_id", "connectorId")
        purpose = _kw("charging_profile_purpose", "chargingProfilePurpose")
        stack_level = _kw("stack_level", "stackLevel")
        if profile_id is not None:
            profile_id = int(profile_id)
        if conn_id is not None:
            conn_id = int(conn_id)
        if stack_level is not None:
            stack_level = int(stack_level)

        before = len(self._charger._charging_profiles)
        remaining = [
            p for p in self._charger._charging_profiles
            if not profile_matches_clear(p, profile_id, conn_id, purpose, stack_level)
        ]
        self._charger._charging_profiles = remaining
        removed = before - len(remaining)

        if removed > 0:
            cp_id = self._charger.charge_point_id
            profiles_copy = list(remaining)
            asyncio.create_task(asyncio.to_thread(save_profiles, cp_id, profiles_copy))
            return call_result.ClearChargingProfilePayload(status=ClearChargingProfileStatus.accepted)
        return call_result.ClearChargingProfilePayload(status=ClearChargingProfileStatus.unknown)

    async def _resume_evse_if_profile_available(self, connector_id: int) -> None:
        """Resume a SuspendedEVSE connector if a valid charging profile now exists for it."""
        charger = self._charger
        if charger is None:
            return
        evse = charger.get_evse(connector_id)
        if evse is None or evse.transaction_id is None:
            return
        if evse.state != EvseState.SuspendedEVSE:
            return
        if connector_id in charger._meter_tasks:
            return  # meter loop already running
        if charger.get_limit_W(connector_id) is None:
            return  # still no valid profile

        # Resume: Charging state + new metering loop
        evse.transition_to(EvseState.Charging)
        await self.send_status_notification(connector_id, EvseState.Charging)

        send_meter_values = self._make_send_meter_values(evse, connector_id, charger)
        limit_fn = lambda: charger.get_limit_W(connector_id)  # noqa: E731

        async def on_soc_full_resume() -> None:
            evse.transition_to(EvseState.SuspendedEV)
            active_cp = charger._ocpp_client
            cp = active_cp if active_cp is not None else self
            await cp.send_status_notification(connector_id, EvseState.SuspendedEV)

        async def on_no_profile_resume() -> None:
            evse.transition_to(EvseState.SuspendedEVSE)
            active_cp = charger._ocpp_client
            cp = active_cp if active_cp is not None else self
            await cp.send_status_notification(connector_id, EvseState.SuspendedEVSE)
            charger._meter_tasks.pop(connector_id, None)

        from simulator_core.meter_engine import start_metering_loop as _start_loop
        task, stop_event = _start_loop(
            evse,
            send_meter_values,
            charger.get_meter_measurands(),
            charger.get_meter_interval_s(),
            on_soc_full=on_soc_full_resume,
            limit_fn=limit_fn,
            on_no_profile=on_no_profile_resume,
        )
        charger._meter_tasks[connector_id] = (task, stop_event)

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
        # Dispatch to offline path when charger is in offline mode
        if self._charger.is_offline_mode():
            return await self._start_transaction_offline(
                connector_id, id_tag,
                start_soc_pct=start_soc_pct, battery_capacity_kwh=battery_capacity_kwh,
            )
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

        charger = self._charger  # confirmed non-None above; capture for closures
        send_meter_values = self._make_send_meter_values(evse, connector_id, charger)

        async def on_soc_full() -> None:
            evse.transition_to(EvseState.SuspendedEV)
            # Use the currently-active CP so this works correctly after a reconnect
            active_cp = charger._ocpp_client
            cp = active_cp if active_cp is not None else self
            await cp.send_status_notification(connector_id, EvseState.SuspendedEV)

        async def on_no_profile() -> None:
            evse.transition_to(EvseState.SuspendedEVSE)
            active_cp = charger._ocpp_client
            cp = active_cp if active_cp is not None else self
            await cp.send_status_notification(connector_id, EvseState.SuspendedEVSE)
            charger._meter_tasks.pop(connector_id, None)

        interval_s = charger.get_meter_interval_s()
        measurands = charger.get_meter_measurands()
        limit_fn = lambda: charger.get_limit_W(connector_id)  # noqa: E731
        task, stop_event = start_metering_loop(
            evse, send_meter_values, measurands, interval_s,
            on_soc_full=on_soc_full,
            limit_fn=limit_fn,
            on_no_profile=on_no_profile,
        )
        # Store on Charger (not self) so tasks survive WS reconnects
        self._charger._meter_tasks[connector_id] = (task, stop_event)
        return resp.transaction_id

    async def stop_transaction(self, connector_id: int, reason: Reason = Reason.local) -> bool:
        """Stop charging: stop metering, send StopTransaction, transition EVSE to Available."""
        if not self._charger:
            return False
        evse = self._charger.get_evse(connector_id)
        if not evse or evse.transaction_id is None:
            return False

        # Meter tasks live on Charger so they survive reconnects
        task_stop = self._charger._meter_tasks.pop(connector_id, None)
        if task_stop:
            task, stop_event = task_stop
            stop_event.set()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, ConnectionClosed):
                # CancelledError: normal task cancellation.
                # ConnectionClosed: the WS closed while the meter loop was mid-tick
                # (e.g. CSMS sent RemoteStopTransaction then immediately closed the connection).
                # In both cases the meter task is done; discard the exception.
                pass

        transaction_id = evse.transaction_id
        evse.transition_to(EvseState.Finishing)
        await self.send_status_notification(connector_id, EvseState.Finishing)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        local_tx = transaction_id if transaction_id is not None and transaction_id < 0 else None
        req = call.StopTransactionPayload(
            meter_stop=int(evse.energy_Wh),
            timestamp=now,
            transaction_id=transaction_id,
            reason=reason,
            id_tag=None,
        )
        # Cache if offline, send if online
        await self._send_or_cache(req, connector_id=connector_id, local_tx_id=local_tx)

        evse.end_transaction()
        evse.transition_to(EvseState.Available)
        await self.send_status_notification(connector_id, EvseState.Available)
        return True


    async def _start_transaction_offline(
        self,
        connector_id: int,
        id_tag: str,
        *,
        start_soc_pct: Optional[float] = None,
        battery_capacity_kwh: Optional[float] = None,
    ) -> Optional[int]:
        """Start a transaction while offline: generate a local negative tx ID, cache OCPP messages.

        The local transaction ID is reconciled with the CSMS-assigned ID during replay.
        """
        charger = self._charger
        if not charger:
            return None
        evse = charger.get_evse(connector_id)
        if not evse or evse.transaction_id is not None:
            return None
        if not evse.transition_to(EvseState.Preparing):
            return None

        await self.send_status_notification(connector_id, EvseState.Preparing)

        # Resolve vehicle params
        if start_soc_pct is None or battery_capacity_kwh is None:
            resolver = charger.get_vehicle_resolver()
            result = resolver(id_tag) if resolver else None
            if start_soc_pct is None:
                start_soc_pct = result[1] if result else 20.0
            if battery_capacity_kwh is None:
                battery_capacity_kwh = result[0] if result else 100.0

        local_tx_id = charger.next_offline_transaction_id()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        evse.start_transaction(
            local_tx_id, id_tag,
            start_soc_pct=start_soc_pct,
            battery_capacity_wh=battery_capacity_kwh,
        )
        if not evse.transition_to(EvseState.Charging):
            evse.end_transaction()
            evse.transition_to(EvseState.Available)
            await self.send_status_notification(connector_id, EvseState.Available)
            return None

        # Cache StartTransaction (will be sent to CSMS on replay)
        start_req = call.StartTransactionPayload(
            connector_id=connector_id,
            id_tag=id_tag,
            meter_start=int(evse.energy_Wh),
            timestamp=now,
        )
        await self._send_or_cache(start_req, connector_id=connector_id, local_tx_id=local_tx_id)
        await self.send_status_notification(connector_id, EvseState.Charging)

        send_meter_values = self._make_send_meter_values(evse, connector_id, charger)

        async def on_soc_full() -> None:
            evse.transition_to(EvseState.SuspendedEV)
            # Use the currently-active CP if online (avoids AttributeError on ephemeral/stale self)
            active_cp = charger._ocpp_client
            cp = active_cp if active_cp is not None else self
            await cp.send_status_notification(connector_id, EvseState.SuspendedEV)

        async def on_no_profile() -> None:
            evse.transition_to(EvseState.SuspendedEVSE)
            active_cp = charger._ocpp_client
            cp = active_cp if active_cp is not None else self
            await cp.send_status_notification(connector_id, EvseState.SuspendedEVSE)
            charger._meter_tasks.pop(connector_id, None)

        interval_s = charger.get_meter_interval_s()
        measurands = charger.get_meter_measurands()
        limit_fn = lambda: charger.get_limit_W(connector_id)  # noqa: E731
        task, stop_event = start_metering_loop(
            evse, send_meter_values, measurands, interval_s,
            on_soc_full=on_soc_full,
            limit_fn=limit_fn,
            on_no_profile=on_no_profile,
        )
        charger._meter_tasks[connector_id] = (task, stop_event)
        return local_tx_id


def _patch_meter_values_tx_id(payload: call.MeterValuesPayload, real_tx_id: int) -> call.MeterValuesPayload:
    """Return a new MeterValuesPayload with the transaction_id replaced."""
    return call.MeterValuesPayload(
        connector_id=payload.connector_id,
        transaction_id=real_tx_id,
        meter_value=payload.meter_value,
    )


def _patch_stop_transaction_tx_id(payload: call.StopTransactionPayload, real_tx_id: int) -> call.StopTransactionPayload:
    """Return a new StopTransactionPayload with the transaction_id replaced."""
    return call.StopTransactionPayload(
        meter_stop=payload.meter_stop,
        timestamp=payload.timestamp,
        transaction_id=real_tx_id,
        reason=payload.reason,
        id_tag=payload.id_tag,
    )


async def replay_cached_messages(charger: Charger, cp: SimulatorChargePoint) -> None:
    """Replay OCPP messages cached during offline operation.

    Messages are sent in the order they were cached. For offline-started transactions
    (local_transaction_id < 0), the CSMS-assigned transaction_id from the StartTransaction
    response is used to patch subsequent MeterValues and StopTransaction payloads.
    """
    messages = charger.pop_message_cache()
    if not messages:
        return
    LOG.info("Replaying %d cached OCPP message(s) for %s", len(messages), charger.charge_point_id)

    # Map local (negative) tx_id -> real CSMS tx_id
    tx_id_map: dict[int, int] = {}

    for msg in messages:
        try:
            if msg.message_type == "StatusNotification":
                await cp.call(msg.payload)

            elif msg.message_type == "StartTransaction":
                resp = await cp.call(msg.payload)
                if resp is not None and resp.transaction_id > 0 and msg.local_transaction_id is not None:
                    real_id = resp.transaction_id
                    local_id = msg.local_transaction_id
                    tx_id_map[local_id] = real_id
                    LOG.info("Replay: mapped local tx %d -> CSMS tx %d", local_id, real_id)
                    # Patch live EVSE with the real transaction_id
                    evse = charger.get_evse(msg.connector_id)
                    if evse is not None and evse.transaction_id == local_id:
                        evse.transaction_id = real_id

            elif msg.message_type == "MeterValues":
                payload = msg.payload
                local_tx = msg.local_transaction_id
                if local_tx is not None and local_tx in tx_id_map:
                    payload = _patch_meter_values_tx_id(payload, tx_id_map[local_tx])
                await cp.call(payload)

            elif msg.message_type == "StopTransaction":
                payload = msg.payload
                tx_id = getattr(payload, "transaction_id", None)
                if tx_id is not None and tx_id in tx_id_map:
                    payload = _patch_stop_transaction_tx_id(payload, tx_id_map[tx_id])
                await cp.call(payload)

            else:
                LOG.debug("Replay: skipping unrecognised message type %s", msg.message_type)

        except Exception as e:
            LOG.warning("Replay error for %s (connector %d): %s", msg.message_type, msg.connector_id, e)


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
            """Send BootNotification, StatusNotification per EVSE, then replay any offline-cached messages."""
            await cp.send_boot_notification()
            for evse in charger.evses:
                status = evse.state if evse.state else EvseState.Available
                await cp.send_status_notification(evse.evse_id, status)
            # Replay messages that were cached during offline operation
            await replay_cached_messages(charger, cp)

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

        # Offline wait: if charger is in offline mode, hold here until set_online() is called.
        # Meter tasks keep running on Charger; sends are cached via _send_or_cache.
        if charger.is_offline_mode():
            LOG.info("Charger %s is in offline mode — waiting for go-online", charger.charge_point_id)
            await charger.wait_for_online()
            if charger.should_stop_connect():
                break
            LOG.info("Charger %s exited offline mode — reconnecting", charger.charge_point_id)
            # Reset backoff for clean reconnect after intentional offline period
            delay = base_delay
        else:
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
