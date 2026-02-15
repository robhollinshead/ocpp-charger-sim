# OCPP Charger Simulator

Standalone **OCPP 1.6J charger simulator** with a web UI and Python backend. It simulates one or more charge points and connects to any OCPP 1.6J CSMS over WebSocket. Use it for development and testing alongside your CSMS on the same machine.

## Prerequisites

- **Node.js** and **npm** (or bun) — for the frontend
- **Python 3.11+** — for the backend
- **Docker** and **Docker Compose** (optional) — for containerised runs

## Ports

To avoid clashes with a CSMS running on the same machine:

| Service    | Backend port | Frontend port |
| ---------- | ------------ | ------------- |
| CSMS       | 8000         | 5173          |
| Simulator  | **8001**     | **8080**      |

## Running locally

### Backend

From the project root:

```bash
cd backend
make install
make run
```

Or from the root: `make -C backend run`.

The API runs at **http://localhost:8001**. Optional: copy `backend/.env.example` to `backend/.env` and set `PORT=8001` (or another port).

### Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The UI is at **http://localhost:8080**.

## Docker

Build and run the simulator (backend serves the built frontend):

```bash
docker compose up --build
```

- **API and UI**: http://localhost:8001  
- **Health**: http://localhost:8001/health  

Ports 8000 and 5173 are left free for the CSMS.

## Testing

- **Backend**: `cd backend && make test` (full suite). See [docs/testing.md](docs/testing.md) for `test-unit`, `test-integration`, `test-api`, `test-quick`, and `test-coverage`.
- **Frontend**: `cd frontend && npm run test` (or `npm run test:run`, `npm run test:watch`, `npm run test:coverage`).
- **Both**: from repo root, `make test` runs backend and frontend tests.

Tests use an in-memory DB and never touch production; see **Database safety** and **Test maintenance** in [docs/testing.md](docs/testing.md).

## Project structure

```
charger-sim-ocpp/
├── backend/          FastAPI service (OCPP simulator core, API)
├── frontend/         React + Vite + TypeScript UI
├── docs/             Technical documentation (architecture, OCPP support, UI guide, etc.)
├── scripts/          Doc tooling (screenshot capture, PDF build)
├── data/             Optional CSV/JSON for charger and vehicle import
├── plans/            Implementation and OCPP design docs
├── Dockerfile        Multi-stage build (frontend + backend)
├── docker-compose.yml
└── README.md
```

## Technical documentation

Markdown docs are in [docs/](docs/). Start with [docs/README.md](docs/README.md) for the index (architecture, OCPP support, edge cases, UI guide, out-of-scope).

### Technical documentation (PDF)

To generate a PDF that includes the docs (and optional UI screenshots):

1. **Install doc dependencies** (from repo root): `npm install`
2. **Optional — capture screenshots:** Run the frontend (and optionally the backend), then:
   ```bash
   npm run docs:screenshots
   ```
   Screenshots are written to `docs/screenshots/` and referenced in [docs/ui-guide.md](docs/ui-guide.md).
3. **Build the PDF:**
   ```bash
   npm run docs:pdf
   ```
   Output: `docs/build/technical-documentation.pdf`.

## Next steps

See [plans/Implementation_plan.md](plans/Implementation_plan.md) for Phase 2 (core simulator engine, OCPP client, EVSE state machine, meter values) and later phases.
