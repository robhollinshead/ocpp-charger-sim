# Supported OCPP functionality

The simulator implements **OCPP 1.6J** as a charge point. This document lists the message types and configuration keys supported.

## Outgoing messages (charger → CSMS)

| Action | When |
|--------|------|
| **BootNotification** | On WebSocket connect; includes charge_point_vendor, charge_point_model, firmware_version from charger. |
| **StatusNotification** | On every EVSE state change (e.g. Available, Preparing, Charging, SuspendedEV, Finishing, Faulted). When the simulated vehicle reaches 100% SoC, the EVSE transitions to **SuspendedEV** and a StatusNotification is sent so the CSMS can re-allocate power. |
| **Authorize** | Before StartTransaction when `OCPPAuthorizationEnabled` is true; otherwise skipped (free vend). |
| **StartTransaction** | When starting a charging session (connectorId, idTag, meter start, timestamp). |
| **StopTransaction** | When stopping a session (meter stop, transactionId, reason, timestamp). |
| **MeterValues** | Periodically per EVSE while Charging or SuspendedEV (active transaction); interval from `MeterValuesSampleInterval`. Continues after transition to SuspendedEV (at 100% SoC) with 0 power until the session is stopped. |
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

- **GetConfiguration** with no keys returns all known keys present in config; with a list of keys returns those that are known and reports the rest in `unknown_key`.
- **ChangeConfiguration** accepts integer keys (HeartbeatInterval, ConnectionTimeOut, MeterValuesSampleInterval, ClockAlignedDataInterval) and boolean keys (AuthorizeRemoteTxRequests, LocalAuthListEnabled, OCPPAuthorizationEnabled). Unknown key → NotSupported; invalid value → Rejected.

## MeterValues

- One **asyncio metering loop** per EVSE while it is in **Charging** or **SuspendedEV** state with an active transaction. The loop keeps running after the EVSE transitions to SuspendedEV so the CSMS continues to receive MeterValues (with 0 power) until the session is stopped.
- **Energy** increases monotonically while charging; **power** comes from the CSMS via SetChargingProfile (effective power from EVSE). When the EVSE is in **SuspendedEV** or **SuspendedEVSE**, effective power is **0** regardless of SetChargingProfile, so no further energy is simulated.
- **SoC** is always calculated internally (for both AC and DC). When SoC reaches **100%**, the simulator transitions the EVSE to **SuspendedEV**, sends StatusNotification(SuspendedEV), and effective power becomes 0; the meter loop continues.
- **Voltage** is dynamically computed from the current SoC using a sigmoid-based OCV (open-circuit voltage) model for a 108-cell DC pack.
- Payload includes Energy.Active.Import.Register (Wh), Power.Active.Import (W), Current.Import (A). **DC chargers** also include SoC (Percent, location EV); **AC chargers** do not send SoC in MeterValues (per typical real AC behaviour) but still track it internally for the 100% → SuspendedEV transition.
- Interval is configurable via `MeterValuesSampleInterval` (default 30 seconds).
