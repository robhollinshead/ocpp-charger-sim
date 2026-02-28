# CLAUDE.md — Backend Tests

This file provides guidance for `backend/tests/`.

## Test Layout

```
tests/
  conftest.py          # Shared fixtures (engine, db_session, client)
  api/                 # API endpoint tests (marker: api)
  unit/                # Unit tests for simulator_core and utils (marker: unit)
  integration/         # Repository-level DB tests (marker: integration)
```

Pytest markers: `unit`, `integration`, `api`, `regression`, `slow`

## Running Tests

```bash
make test                 # All suites
make test-unit            # pytest -m unit
make test-integration     # pytest -m integration
make test-api             # pytest -m api
make test-quick           # API only (fastest feedback)
make test-coverage        # All + HTML report (80% minimum required)
```

Run a single test file:
```bash
cd backend
pytest tests/unit/test_ocpp_client.py -v
```

Run a single test:
```bash
pytest tests/unit/test_ocpp_client.py::test_boot_notification -v
```

## Core Fixtures (`conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `engine` | session | In-memory SQLite engine (all tables created once) |
| `db_session` | function | Transactional session, rolled back after each test |
| `client` | function | FastAPI `TestClient` with `get_db` overridden to use `db_session` |

**Never bypass these fixtures** — they ensure tests never touch the production DB.

## Database Safety Rules

- Tests set `TESTING=true` + `TESTING_DATABASE_URL=sqlite:///:memory:`
- `db.py` raises `RuntimeError` if `TESTING=true` but the URL contains `simulator.db`
- In-memory SQLite uses `StaticPool` (single connection shared across the session)
- Each test function gets a fresh transaction that is rolled back — never commit in tests

## Testing Patterns

- **Arrange–Act–Assert** structure within each test
- **Patch where used**, not where defined: `patch("backend.api.chargers.store")` not `patch("backend.simulator_core.store.store")`
- Prefer fixtures over inline setup for shared resources
- Mark tests with the appropriate marker (`@pytest.mark.unit`, etc.)
- For async code under test, `pytest-asyncio` handles the event loop (`asyncio_mode = auto` in `pytest.ini`)

## Coverage Requirement

80% minimum backend coverage. Check with `make test-coverage`. If adding new modules, add corresponding tests to maintain coverage.
