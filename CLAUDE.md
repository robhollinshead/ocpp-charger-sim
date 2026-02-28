# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OCPP 1.6J Charger Simulator — simulates one or more EV charge points and connects to any OCPP 1.6J CSMS (Charging Station Management System) over WebSocket. Consists of a Python FastAPI backend and React/TypeScript frontend.

**Port allocation:** Backend: 8001 | Frontend dev server: 8080 | CSMS (external): 8000 or 5173

## Development Commands

### Backend
```bash
cd backend
make install        # Install Python dependencies
make run            # Start FastAPI with hot reload (port 8001)
make test           # Full test suite
make test-unit      # Unit tests only
make test-integration  # Integration tests only
make test-api       # API tests only
make test-quick     # API tests only (fastest)
make test-coverage  # Full suite + coverage report (80% minimum)
```

### Frontend
```bash
cd frontend
npm install
npm run dev         # Dev server on port 8080
npm run build       # Production build
npm run lint        # ESLint
npm run test        # Vitest (watch mode)
npm run test:run    # Vitest (single run)
npm run test:coverage  # With coverage
```

### Full project
```bash
make test           # Run all backend and frontend tests
docker compose up --build  # Build and run in Docker (single container, port 8001)
```

## Architecture

See [backend/CLAUDE.md](backend/CLAUDE.md) for backend detail and [frontend/CLAUDE.md](frontend/CLAUDE.md) for frontend detail.

### System Components

```
Browser → Frontend (React/Vite) → Backend REST API (FastAPI)
                                        ↓
                               SQLite (dev) / PostgreSQL (prod)
                                        ↓
                          simulator_core (in-memory charger state)
                                        ↓
                          CSMS ← WebSocket (OCPP 1.6J)
```

### Key Architectural Decisions

- **In-memory state:** Charger/EVSE simulator state lives in `simulator_core/store.py` (a dict keyed by `charge_point_id`). DB persistence is for configuration and history; live state is in-memory.
- **Async OCPP client:** Each connected charger runs an asyncio task (`ocpp_client.py`) for WebSocket communication. The meter engine runs a separate async loop sending periodic MeterValues.
- **Static serving:** In production (Docker), `SERVE_STATIC=1` causes the backend to serve the frontend build from `/static`.
- **DB safety:** `db.py` raises `RuntimeError` if `TESTING=true` but the DB URL points to the production file. Tests always use in-memory SQLite.

### Backend Structure

| Path | Role |
|------|------|
| `backend/main.py` | FastAPI app, startup hooks (migrations + charger hydration) |
| `backend/db.py` | Engine factory, session dependency, safety guard |
| `backend/api/` | REST routers: chargers, locations, vehicles, import |
| `backend/models/` | SQLAlchemy ORM models |
| `backend/repositories/` | DB access layer |
| `backend/schemas/` | Pydantic request/response models |
| `backend/simulator_core/` | OCPP engine: charger, EVSE, OCPP client, meter engine, store |
| `backend/alembic/` | DB migrations |

### Frontend Structure

| Path | Role |
|------|------|
| `frontend/src/pages/` | Route-level page components |
| `frontend/src/components/` | Shared and feature components |
| `frontend/src/components/charger/` | Charger detail tabs (Configuration, Logs, Transactions, Scenarios) |
| `frontend/src/components/ui/` | shadcn/ui primitives |
| `frontend/src/api/` | React Query hooks for each resource |

### Route Structure

```
/                                    → LocationList
/location/:locationId                → LocationDetail
/location/:locationId/charger/:id    → ChargerDetail (tabs: Config, Logs, Transactions, Scenarios)
```

## Tech Stack

**Backend:** Python 3.11+, FastAPI, Uvicorn, OCPP library, SQLAlchemy 2, Alembic, Pytest
**Frontend:** React 18, React Router 6, TypeScript, Vite/SWC, TanStack Query, shadcn/ui, Tailwind CSS, React Hook Form + Zod, Vitest, Recharts, Sonner, Lucide React
