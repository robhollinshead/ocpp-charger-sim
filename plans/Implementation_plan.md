# Implementation Plan — Standalone OCPP Charger Simulator (Web UI Edition)

This document is a detailed, actionable implementation plan for building a **standalone OCPP 1.6J Charger Simulator** with a web-based UI, independent from the existing CSMS backend.

The plan is structured into phases, with clear deliverables, module responsibilities, and recommended sequencing for an AI coding agent or engineering team.

---

## 1. Overview

The goal is to build a standalone OCPP simulator application that includes:

- **Backend** — Python simulator service (FastAPI)
- **Frontend** — Modern web UI (React / Svelte / Vue)
- **Simulation** — Multi-charger, multi-location environment with scenario engine and chaos injection
- **OCPP** — Charger & EVSE simulation with full OCPP 1.6J message support
- **Data** — CSV/JSON import for chargers and vehicles/tags
- **Operations** — Real-time logs and charger configuration controls

The simulator should connect to **any OCPP 1.6J CSMS** via WebSocket.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  Web UI (React / Vue / Svelte)               │
│   Dashboard · Chargers · Locations · Scenarios · Logs         │
└──────────────────────────────────┬───────────────────────────┘
                                   │
                         REST API / WebSocket
                                   │
┌──────────────────────────────────────────────────────────────┐
│             Backend Simulator (Python + FastAPI)              │
│                                                              │
│  • OCPP Charger Simulation Core (async)                      │
│  • EVSE State Machine                                        │
│  • MeterValues Engine                                        │
│  • Charger Config Store                                      │
│  • Scenario Engine                                           │
│  • Chaos Event Engine                                        │
│  • Multi-Location Manager                                    │
│  • Charger / Vehicle Importers                               │
│  • Logging Engine                                            │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. Repository Structure

```
ocpp-simulator/
├── backend/
│   ├── main.py
│   ├── api/
│   ├── simulator_core/
│   ├── schemas/
│   └── utils/
├── frontend/
│   ├── src/
│   ├── index.html
│   └── package.json
├── data/
├── tests/
└── README.md
```

---

## 4. Phase-by-Phase Implementation

Each phase expands the simulator towards full functionality.

---

### Phase 1 — Backend & Frontend Bootstrap

**Goals**

- Initialize project structure
- Establish backend with FastAPI
- Establish frontend build system

**Deliverables**

- `backend/main.py` with API scaffolding
- Basic health endpoint: `GET /health`
- Frontend scaffold (React, Svelte, or Vue)
- Shared models directory
- Docker files (optional)

---

### Phase 2 — Core Simulator Engine

**Goals**

- Implement the foundational simulation components

#### 2.1 ChargePoint Simulation

- **Module:** `ocpp_client.py` (async OCPP client)
- **Handles:** BootNotification, StatusNotification, Authorize (dummy), StartTransaction, StopTransaction, MeterValues, SetChargingProfile
- Reconnect logic for chaos events

#### 2.2 EVSE State Machine

| State          | Description   |
|----------------|---------------|
| Available      | Ready for use |
| Preparing      | Pre-charge    |
| Charging       | Active charge |
| SuspendedEV / SuspendedEVSE | Paused |
| Finishing      | Winding down  |
| Faulted        | Error state   |
| Unavailable    | Out of service|

- Validation of transitions
- Event-driven updates

#### 2.3 MeterValues Engine

- Runs per-EVSE asyncio task
- **Rules:** Energy increases monotonically; power follows charger max or CSMS profile; `current = power / voltage`
- Configurable interval (default 10s)

**Deliverables**

- Fully functioning charger + EVSE simulation model
- Internal tick-based meter generation
- Backend endpoints: `GET /chargers`, `GET /chargers/{id}`

---

### Phase 3 — Location System & Data Importers

**Goals**

- Enable multi-location simulations and import logic

#### 3.1 Location Management

- Create / edit / delete locations
- Activate location (single active context)
- Persist chargers and vehicles per location
- **APIs:** `GET` / `POST` / `DELETE` / `PATCH` `/locations`, `POST /locations/activate/{id}`

#### 3.2 Importers

| Importer   | Formats   | Validation                         |
|------------|-----------|------------------------------------|
| Chargers   | CSV, JSON | Duplicate IDs, EVSE structure      |
| Vehicles   | CSV, JSON | idTags                             |

- Attach imported data to active location
- **APIs:** `POST /import/chargers`, `POST /import/vehicles`

**Deliverables**

- Import pipeline
- Location store and active context

---

### Phase 4 — Scenario Engine & Chaos Events

**Goals**

- Introduce simulation scenarios and controlled chaos events

#### 4.1 Scenario Engine

Base interface:

- `on_start()`
- `on_tick(delta_t)`
- `on_event(event)`
- `on_stop()`

#### 4.2 Built-In Scenarios

| Scenario          | Description                          |
|-------------------|--------------------------------------|
| `normal_charge`   | Standard charging behaviour          |
| `morning_rush`    | Peak load simulation                 |
| `fluctuating_power` | Power variation over time         |
| `offline_fault`   | Simulated connectivity loss          |
| `chaos_mix`       | Randomized disconnects / faults      |

**APIs:** `POST /scenarios/run`, `POST /scenarios/stop`, `GET /scenarios/status`, `GET /scenarios/list`

#### 4.3 Chaos Events

- Fault EVSE
- Disconnect charger from CSMS
- Random power spikes / drops
- SuspendedEV / SuspendedEVSE injection  
- **API:** `POST /chargers/{id}/chaos`

**Deliverables**

- Fully automated scenario runner
- Chaos tools available in backend

---

### Phase 5 — Web UI Implementation

**Goals**

- Expose all simulator functionality in a rich frontend UI

#### 5.1 Dashboard

- Overview metrics
- Active scenario status
- Active location selector

#### 5.2 Charger List

- Table of all chargers in active location
- State indicators
- Quick actions

#### 5.3 Charger Detail View

Tabs: **Status** (EVSEs, sessions, live charts) · **Configuration** (edit config keys) · **Logs** (live streaming) · **Actions** (start/stop, set states, inject chaos)

#### 5.4 Location Manager

- Create / edit / delete locations
- Activate location
- Assign chargers and vehicles

#### 5.5 Scenario Runner

- Scenario selection
- Parameter configuration
- Live timeline of events

#### 5.6 Import Data

- Upload chargers (CSV/JSON)
- Upload vehicles
- Live validation and preview

#### 5.7 Logs Viewer

- Global and per-charger logs
- Export buttons

**Deliverables**

- Fully functional web UI integrated with backend APIs

---

### Phase 6 — Logging System

**Goals**

- Provide robust per-charger and global logs

**Features**

- Circular log buffer per charger
- Global log stream
- Download logs as text or JSON
- **Filters:** charger, timestamp, event type, OCPP vs scenario vs EVSE state

**APIs**

- `GET /chargers/{id}/logs`
- `DELETE /chargers/{id}/logs`
- `GET /logs`
- `GET /logs/export`

**Deliverables**

- Complete logging engine
- UI log viewer

---

### Phase 7 — Testing & Stabilization

**Goals**

- Ensure reliability and simulation correctness

#### Unit Tests

- State machine transitions
- MeterValues physics calculations
- OCPP client encoding / decoding
- Importer validation

#### Integration Tests

- Boot → StartTransaction → MeterValues → StopTransaction
- Scenarios (`morning_rush`, `chaos_mix`)
- Multi-location switching

#### Performance

- Scale to 50+ chargers
- Avoid asyncio task leaks
- Stable WebSocket handling

**Deliverables**

- Test suite with high coverage
- Scenario replay consistency

---

## 5. API Summary

### Chargers

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/chargers` | List chargers |
| GET    | `/chargers/{id}` | Charger detail |
| POST   | `/chargers/{id}/start` | Start charger |
| POST   | `/chargers/{id}/stop` | Stop charger |
| POST   | `/chargers/{id}/chaos` | Inject chaos |
| GET    | `/chargers/{id}/config` | Get config |
| POST   | `/chargers/{id}/config` | Update config |

### Locations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/locations` | List locations |
| POST   | `/locations` | Create location |
| PATCH  | `/locations/{id}` | Update location |
| DELETE | `/locations/{id}` | Delete location |
| POST   | `/locations/activate/{id}` | Set active location |

### Scenarios

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/scenarios/list` | List scenarios |
| POST   | `/scenarios/run` | Start scenario |
| POST   | `/scenarios/stop` | Stop scenario |
| GET    | `/scenarios/status` | Scenario status |

### Import

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | `/import/chargers` | Import chargers |
| POST   | `/import/vehicles` | Import vehicles |

### Logs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/logs` | Global logs |
| GET    | `/logs/export` | Export logs |
| GET    | `/chargers/{id}/logs` | Charger logs |
| DELETE | `/chargers/{id}/logs` | Clear charger logs |

---

## 6. Success Criteria

The simulator is complete when:

- [ ] It runs standalone with web UI control
- [ ] It can connect to any CSMS OCPP endpoint
- [ ] It simulates realistic charger behaviour (state, meter, profiles)
- [ ] Multi-location support is stable and user-friendly
- [ ] Scenarios run deterministically with visible UI feedback
- [ ] Chaos injection works safely
- [ ] Data import/export is reliable
- [ ] Logging is comprehensive and easy to browse

---

## 7. Out of Scope / Future Enhancements

These may be added later but are **not** required for the initial implementation:

- **Connection retries**: Add an optional cap on WebSocket connection retries (e.g. max N attempts or “give up after M minutes”) so that “Connect” does not retry indefinitely if the CSMS is permanently unavailable. For now, retries use exponential back-off with no cap.
- **Authorize before StartTransaction**: Optional pre-authorisation flow where the charger sends an Authorize request to the CSMS before StartTransaction. Currently idTag is validated only when StartTransaction is sent. Authorize can be added later for idTag validation and caching.
- **Include SoC On Metering**: add vehicle info to make SoC updates realistic
- **UI Updates on Websockets**: make the UI update based on websockets and not constant GET requests
- OCPP 2.0.1 support
- ISO-15118 vehicle integration
- DC fast-charging taper curves
- Dynamic scenario editor in UI
- Hardware-in-the-loop mode
- Distributed simulation clusters
