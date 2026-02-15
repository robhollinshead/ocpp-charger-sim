# Supported OCPP functionality

The simulator implements **OCPP 1.6J** as a charge point. This document lists the message types and configuration keys supported.

## Outgoing messages (charger → CSMS)

| Action | When |
|--------|------|
| **BootNotification** | On WebSocket connect; includes charge_point_vendor, charge_point_model, firmware_version from charger. |
| **StatusNotification** | On every EVSE state change (e.g. Available, Preparing, Charging, Finishing, Faulted). |
| **Authorize** | Before StartTransaction when `OCPPAuthorizationEnabled` is true; otherwise skipped (free vend). |
| **StartTransaction** | When starting a charging session (connectorId, idTag, meter start, timestamp). |
| **StopTransaction** | When stopping a session (meter stop, transactionId, reason, timestamp). |
| **MeterValues** | Periodically per EVSE while charging; interval from `MeterValuesSampleInterval`. |
| **Heartbeat** | Periodically; interval from `HeartbeatInterval`. |

## Incoming messages (CSMS → charger)

| Action | Behaviour |
|--------|-----------|
| **Authorize** | Dummy handler: always returns Accepted (used when CSMS sends Authorize; simulator does not gate on this for UI-started transactions). |
| **GetConfiguration** | Returns requested or all known config keys; unknown requested keys are returned in `unknown_key`. |
| **ChangeConfiguration** | Validates key and value type; updates in-memory config and persists to DB; returns Accepted, Rejected, or NotSupported. |
| **SetChargingProfile** | Extracts power limit from the first charging schedule period (W or A; A converted using EVSE voltage) and applies to the EVSE; returns Accepted or Rejected. |
| **RemoteStartTransaction** | Starts a transaction on the target connector (or first available if connector_id omitted); returns Accepted or Rejected; actual StartTransaction is sent in a background task. |
| **RemoteStopTransaction** | Stops the transaction identified by transaction_id; returns Accepted or Rejected; actual StopTransaction is sent in a background task. |

## Configuration keys

The following keys are known and can be read/updated via GetConfiguration and ChangeConfiguration:

| Key | Type | Description |
|-----|------|-------------|
| HeartbeatInterval | int | Seconds between Heartbeat messages (default 120). |
| ConnectionTimeOut | int | Connection timeout in seconds. |
| MeterValuesSampleInterval | int | Seconds between MeterValues while charging (default 30). |
| ClockAlignedDataInterval | int | For clock-aligned meter data (config only). |
| AuthorizeRemoteTxRequests | bool | Whether the charge point accepts RemoteStartTransaction. |
| LocalAuthListEnabled | bool | Local auth list enabled flag. |
| OCPPAuthorizationEnabled | bool | If true, simulator sends Authorize before StartTransaction and only starts on Accepted. |
| voltage_V | float | EVSE voltage used for current/power calculations (e.g. 230.0). |

- **GetConfiguration** with no keys returns all known keys present in config; with a list of keys returns those that are known and reports the rest in `unknown_key`.
- **ChangeConfiguration** accepts integer keys (HeartbeatInterval, ConnectionTimeOut, MeterValuesSampleInterval, ClockAlignedDataInterval), boolean keys (AuthorizeRemoteTxRequests, LocalAuthListEnabled, OCPPAuthorizationEnabled), and `voltage_V` (float). Unknown key → NotSupported; invalid value → Rejected.

## MeterValues

- One **asyncio metering loop** per EVSE while it is in Charging state with an active transaction.
- **Energy** increases monotonically; **power** comes from the CSMS via SetChargingProfile (or effective power from EVSE); **current** = power / voltage.
- Payload includes Energy.Active.Import.Register (Wh), Power.Active.Import (W), Current.Import (A), and SoC (Percent, location EV).
- Interval is configurable via `MeterValuesSampleInterval` (default 30 seconds).
