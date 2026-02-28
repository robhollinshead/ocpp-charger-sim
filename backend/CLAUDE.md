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

## Testing

See [tests/CLAUDE.md](tests/CLAUDE.md) for full test guidance.
