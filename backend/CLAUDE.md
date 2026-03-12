# CLAUDE.md — Backend

This file provides guidance for the `backend/` directory of the charger-sim-ocpp project.

## simulator_core — The OCPP Engine

This is the heart of the simulator. All state here is in-memory; DB is only used for persistence on startup and shutdown.

- **`charger.py`** — `Charger` class holds identity (`charge_point_id`), list of `EVSE` objects, OCPP config dict, and an optional reference to the running `OcppClient`.
- **`evse.py`** — `EVSE` state machine. States: `Available → Preparing → Charging → SuspendedEV / SuspendedEVSE → Finishing → Available`. Also holds meter state: `energy_wh`, `power_w`, `soc`, `transaction_id`. SoC progress gates transitions (e.g., `SuspendedEV` at 100% SoC).
- **`ocpp_client.py`** — The main OCPP 1.6J charge point client. Connects via WebSocket to the CSMS, sends BootNotification, StatusNotification, MeterValues, StartTransaction, StopTransaction, Heartbeat, Authorize. Handles inbound: RemoteStartTransaction, RemoteStopTransaction, GetConfiguration, ChangeConfiguration, SetChargingProfile.
- **`meter_engine.py`** — Async loop that ticks periodically, advancing energy/power/SoC on each EVSE that's in a charging state. Sends MeterValues to CSMS on each tick.
- **`store.py`** — Dict-based registry `{charge_point_id: Charger}`. All API handlers look up live charger state here.
- **`config_sync.py`** — Persists OCPP config key changes to DB when `ChangeConfiguration` is received from the CSMS.
- **`dc_voltage.py`** — Voltage curve calculations for DC charger battery simulation.

## API Layer (`backend/api/`)

FastAPI routers, each mounted at `/api`. Dependency injection pattern:

```python
@router.post("/chargers")
async def create_charger(body: ChargerCreate, db: Session = Depends(get_db)):
    ...
```

- `chargers.py` — CRUD + connect/disconnect/start-stop transaction/config. Connect triggers `OcppClient` task creation; disconnect cancels it.
- `locations.py` / `vehicles.py` — Standard CRUD.
- `import_api.py` — Bulk import via CSV/JSON through `backend/utils/parsers.py` and `backend/utils/validators.py`.

## Database Patterns

- SQLAlchemy 2 ORM with `Session` (not async session) — all DB calls are synchronous in FastAPI using `run_in_executor` is not needed; FastAPI handles threading via its thread pool for sync routes.
- Repository pattern: `charger_repository.py`, `location_repository.py`, `vehicle_repository.py` are the only code that touches `db.query(...)`.
- Alembic migrations in `alembic/`. Run automatically on startup (`main.py` calls `alembic upgrade head`).
- `power_type` field on Charger (`AC` / `DC`) is loaded from DB at startup and synced on hydrate; gates SoC calculations in the EVSE/meter engine.

## Startup Sequence (`main.py`)

1. Run Alembic migrations
2. Load all chargers from DB into `store.py`
3. For each charger that has a CSMS URL and `auto_connect=True`, create an `OcppClient` task
4. Seed default locations if none exist

## Offline Mode

The simulator supports offline charging — sessions survive network outages, messages are cached, and replayed on reconnect.

### Connectivity State Model

`ConnectivityMode` enum (in `charger.py`):
- `ONLINE` — normal operation (default)
- `OFFLINE` — forced offline: WS closed, connect loop waiting, all OCPP sends cached

Set via `charger.set_offline()` / `charger.set_online()`. Independent of `_stop_connect`.

### Key design: `_meter_tasks` lives on `Charger`

Meter tasks are stored in `charger._meter_tasks` (not on `SimulatorChargePoint`). This means tasks survive WS reconnects — the long-lived `Charger` object persists across reconnect cycles, while `SimulatorChargePoint` is re-created on each new connection.

### Message Caching

`CachedMessage` dataclass (in `charger.py`): `message_type`, `payload`, `connector_id`, `local_transaction_id`, `timestamp`.

When offline, `SimulatorChargePoint._send_or_cache()` routes outgoing OCPP calls to `charger.cache_message()` instead of `self.call()`. This intercepts: StatusNotification, StartTransaction, StopTransaction, MeterValues.

### Offline Transactions

Starting a transaction while offline uses `_start_transaction_offline()`:
- Generates a local negative transaction ID (`-1`, `-2`, …) from `charger.next_offline_transaction_id()`
- Caches StartTransaction with the local ID
- EVSE transitions to Charging; meter loop starts normally

### Replay on Reconnect

`replay_cached_messages(charger, cp)` runs in `boot_and_status()` after reconnect:
1. Sends StatusNotifications (no ID patching needed)
2. Sends StartTransaction → gets real CSMS transaction_id → builds `tx_id_map` (local → real)
3. Patches MeterValues and StopTransaction payloads with real IDs before sending
4. Updates live EVSE `transaction_id` to real ID so subsequent meter ticks use correct ID

### TxDefaultPowerW

Config key `TxDefaultPowerW` (float, default `7400.0` W) provides fallback power when no `SetChargingProfile` has been received. Stored in `charger.config`, propagated to `evse.tx_default_power_W` at init and on config update. Used by `evse.get_effective_power_W()` when `offered_limit_W == 0.0`.

### API Endpoints

- `POST /chargers/{id}/go-offline` (204) — Enter offline mode: close WS, keep meter running, cache sends. Idempotent.
- `POST /chargers/{id}/go-online` (202) — Exit offline mode: reconnect loop resumes, cached messages replayed. Returns `{status, cached_messages}`.

### Testing

- `tests/unit/test_offline_mode.py` — ConnectivityMode, CachedMessage, TxDefaultPowerW, meter loop caching
- `tests/unit/test_replay.py` — `replay_cached_messages`, patch helpers, full offline session, tx ID reconciliation
- `tests/api/test_offline_api.py` — go-offline/go-online endpoints, offline start/stop transaction, TxDefaultPowerW config

## Testing

See [tests/CLAUDE.md](tests/CLAUDE.md) for full test guidance.
