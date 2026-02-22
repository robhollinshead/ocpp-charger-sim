# Edge cases and error behaviour

This document describes how the simulator handles rejections, invalid state transitions, and other edge cases.

## EVSE state machine

The EVSE state machine enforces valid OCPP 1.6 transitions. Invalid transitions are **rejected** (no state change).

| From | Allowed to |
|------|------------|
| Available | Preparing, Unavailable |
| Preparing | Charging, Available, Faulted, Unavailable |
| Charging | Finishing, SuspendedEV, SuspendedEVSE, Faulted, Unavailable |
| SuspendedEV | Charging, Finishing, Faulted, Unavailable |
| SuspendedEVSE | Charging, Finishing, Faulted, Unavailable |
| Finishing | Available, Faulted, Unavailable |
| Faulted | Available, Unavailable |
| Unavailable | Available |

Example: going from Available directly to Charging is not allowed; the simulator must transition via Preparing.

## SuspendedEV at 100% SoC

- The simulator tracks **SoC** for every charging session (AC and DC). When the simulated vehicle reaches **100% SoC**, the EVSE automatically transitions from **Charging** to **SuspendedEV** and sends **StatusNotification(SuspendedEV)** to the CSMS so it can re-allocate power.
- The **meter loop does not stop**: MeterValues continue to be sent at the configured interval, but **effective power is 0** (energy and power in the payload no longer increase). SoC remains at 100% until the session is stopped.
- If the CSMS sends **SetChargingProfile** while the EVSE is in SuspendedEV (or SuspendedEVSE), the limit is stored but **effective power stays 0** until the EVSE returns to Charging (e.g. after a future resume flow) or the transaction is stopped.

## Authorize and StartTransaction

- **OCPPAuthorizationEnabled true:** Simulator sends Authorize first. If the CSMS returns non-Accepted or the call fails (e.g. CallError or empty response), the EVSE is reverted to **Available**, a StatusNotification is sent, and **no** StartTransaction is sent.
- **StartTransaction:** If the CSMS returns a rejection, CallError, or empty response, the EVSE is reverted to **Available**, StatusNotification is sent, and no charging or MeterValues are started.
- In both cases the API returns an error to the caller (e.g. "Invalid idTag or transaction rejected by CSMS").

## SetChargingProfile

- **Rejected** when: charger not set, EVSE not found for connector_id, missing or invalid `charging_schedule` / `charging_schedule_period`, or any parse error (TypeError, KeyError, ValueError).
- **Accepted** when: first period's limit is read successfully. If the schedule uses current (A), it is converted to power using the EVSE's voltage (default 230 V).

## RemoteStartTransaction / RemoteStopTransaction

- **Rejected** when: no charger, no target EVSE (or connector_id invalid), or EVSE already has an active transaction. For RemoteStartTransaction, if connector_id is omitted, the first available EVSE is used; if none is available, Rejected.
- **RemoteStopTransaction** looks up the EVSE by transaction_id; if not found, Rejected.
- Both handlers return Accepted/Rejected immediately; the actual StartTransaction/StopTransaction is performed in a **background task** so the OCPP message loop can receive the subsequent request/response.

## ChangeConfiguration

- **NotSupported:** Unknown configuration key.
- **Rejected:** Invalid value for a known key (e.g. non-integer for HeartbeatInterval, non-boolean for OCPPAuthorizationEnabled, non-numeric for voltage_V). Boolean accepts "true"/"1"/"yes" and "false"/"0"/"no".
- If the key/value is valid but **persist to DB fails**, the in-memory config is still updated and the handler returns **Accepted**; the persist failure is logged.

## Vehicle resolution

- When starting a transaction via the API, if the id_tag is not found in the vehicles table, the simulator uses **defaults** (e.g. 100 kWh battery capacity, 20% start SoC) via the charger's vehicle resolver. So starting without a pre-imported vehicle still works with sensible meter/SoC behaviour.
