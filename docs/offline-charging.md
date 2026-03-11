# Offline Charging

Real EV chargers continue charging when network connectivity is lost. The simulator supports this with **offline mode** — a separately-controlled state where the WebSocket connection is intentionally closed while charging sessions continue, OCPP messages are cached, and everything is replayed in the correct order when connectivity is restored.

---

## What is Offline Mode?

When a charger enters offline mode:

- The WebSocket connection to the CSMS is closed (simulating a network outage)
- Active charging sessions **continue** — EVSEs remain in `Charging` state
- The metering loop keeps running and advancing energy/SoC
- All outgoing OCPP messages (StatusNotification, MeterValues, StartTransaction, StopTransaction) are **cached locally in order**
- The connect loop waits — it does not retry until you call go-online

When you restore connectivity (go-online):

- The charger reconnects to the CSMS
- BootNotification and current StatusNotifications are sent first
- All cached messages are **replayed in order**
- Transaction IDs assigned during offline operation are reconciled with CSMS-assigned IDs
- Normal operation resumes automatically

---

## Triggering Offline Mode

### Via API

```bash
# Enter offline mode
POST /api/chargers/{charge_point_id}/go-offline

# Exit offline mode and reconnect
POST /api/chargers/{charge_point_id}/go-online
```

`go-offline` returns `204 No Content`. It is idempotent — calling it twice has no side effects.

`go-online` returns `202 Accepted` with a response body:
```json
{
  "status": "going_online",
  "cached_messages": 12
}
```

### Via UI

On the Charger Detail page, when the charger is connected:
- A **Go Offline** button appears in the header (next to Disconnect)
- Clicking it closes the WebSocket and enters offline mode
- The header shows an amber **Offline** badge with the count of cached messages

When in offline mode:
- A **Go Online** button appears
- Clicking it exits offline mode and triggers reconnection and replay

---

## What Happens During Offline Charging

### Metering

The metering loop continues running at the configured `MeterValuesSampleInterval`. Each tick:

1. Advances `energy_Wh`, `soc_pct`, `power_W`, `current_A` on the EVSE
2. Builds the MeterValues payload
3. **Caches** the payload (instead of sending it over WebSocket)

### Power Determination

Charging power is determined by (in priority order):

1. **Active TxProfile** — if `SetChargingProfile` was received before going offline, `offered_limit_W` is used
2. **TxDefaultPowerW** — if no charging profile was received, this config value is used as the fallback (default: 7400 W = 7.4 kW)

### Starting a Transaction While Offline

You can start a new transaction while offline:

```bash
POST /api/chargers/{charge_point_id}/transactions/start
{
  "connector_id": 1,
  "id_tag": "ABC123"
}
```

Response:
```json
{ "transaction_id": -1 }
```

A **negative transaction ID** indicates a locally-generated ID (e.g. `-1`, `-2`). This is replaced with the CSMS-assigned ID during replay.

### Stopping a Transaction While Offline

You can also stop a transaction while offline:

```bash
POST /api/chargers/{charge_point_id}/transactions/stop
{ "connector_id": 1 }
```

The StopTransaction message is cached and sent to the CSMS on reconnect.

---

## Reconnection and Replay

When `go-online` is called, the connect loop resumes. After a successful WebSocket connection:

1. **BootNotification** — sent to CSMS
2. **StatusNotifications** — one per EVSE, reflecting current state
3. **Cached messages replayed in order**:
   - `StatusNotification` entries — sent as-is
   - `StartTransaction` — sent; CSMS responds with real `transaction_id`; subsequent MeterValues and StopTransaction payloads are automatically patched with the real ID
   - `MeterValues` — sent with correct (patched) transaction ID
   - `StopTransaction` — sent with correct transaction ID; meter stop reflects actual energy delivered

The CSMS receives a coherent history as if the charger had been online the whole time.

---

## TxDefaultPowerW Configuration

`TxDefaultPowerW` is the fallback charging power (in Watts) used when no `SetChargingProfile` has been received from the CSMS.

**Default value:** 7400 W (7.4 kW, typical for a 32A single-phase AC charger)

### Setting via API

```bash
PATCH /api/chargers/{charge_point_id}/config
{ "TxDefaultPowerW": 22000 }
```

### Setting via UI

In the Configuration tab, `TxDefaultPowerW` appears as a numeric field.

### Setting via OCPP ChangeConfiguration

The CSMS can also update this value:
```json
{ "key": "TxDefaultPowerW", "value": "11000" }
```

Changes are applied immediately to all EVSEs on the charger.

---

## Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| Go offline with no active transaction | Offline mode entered; no session affected |
| Go offline during active transaction | Transaction continues; metering and caching proceed normally |
| Start transaction while offline | Local negative tx ID assigned; StartTransaction cached |
| Stop transaction while offline | StopTransaction cached; EVSE returns to Available |
| Long offline duration | All MeterValues cached (no limit); replayed in full on reconnect |
| Reconnect fails (CSMS down) | Connect loop retries with exponential backoff once in ONLINE mode |
| `TxDefaultPowerW = 0` | Zero power charged while offline; energy does not advance |
| Multiple EVSEs with separate transactions | Each EVSE's messages cached independently; replayed in interleaved order |

---

## Example: Full Offline Charging Cycle

```
1. Start charger, connect to CSMS
   → BootNotification, StatusNotification (Available)

2. Start transaction on EVSE 1
   → Authorize, StartTransaction (tx_id=101), StatusNotification (Charging)
   → MeterValues every 30s

3. POST /chargers/CP_001/go-offline
   → WebSocket closed
   → EVSE remains Charging
   → MeterValues continue, cached locally
   → cache grows: [MeterValues×N, ...]

4. (Optional) POST /chargers/CP_001/transactions/stop
   → StopTransaction cached: [MeterValues×N, StopTransaction(tx_id=101)]

5. POST /chargers/CP_001/go-online
   → WebSocket reconnects
   → BootNotification, StatusNotification (Available)
   → Replay: MeterValues×N sent, StopTransaction(tx_id=101) sent

6. CSMS receives complete charging history
```
