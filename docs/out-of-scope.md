# Out-of-scope functionality

The following are **not** part of the current simulator. They may be considered for future enhancements.

## Connection and UI

- **Connection retry cap** — The simulator retries WebSocket connection with exponential backoff when the CSMS is unavailable. There is **no** cap (e.g. max N attempts or "give up after M minutes"); "Connect" can retry indefinitely.
- **UI updates via WebSockets** — The UI refreshes data via REST (e.g. polling/GET). Real-time updates over WebSocket from backend to frontend are not implemented.

## OCPP and standards

- **OCPP 2.0.1** — Only OCPP 1.6J is supported.
- **ISO-15118** — Plug & Charge / vehicle-to-grid communication is not implemented.
- **Other OCPP 1.6 actions** — Any action not explicitly listed in [ocpp-support.md](ocpp-support.md) is unsupported (e.g. DataTransfer, FirmwareStatusNotification, GetDiagnostics, ClearCache, Reset, UnlockConnector, GetCompositeSchedule, CancelReservation, ReserveNow).

## Charging behaviour

- **DC fast-charging taper curves** — The simulator does not model DC tapering; power is driven by SetChargingProfile or default behaviour.
- **Dynamic scenario editor** — Scenarios in the UI are predefined; there is no backend scenario API and no editor to define new scenarios in the UI.
- **Hardware-in-the-loop** — No HIL mode.
- **Distributed simulation clusters** — Single-process simulator only; no distributed or multi-node simulation.
