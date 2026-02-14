# Testing

## Database safety

Tests must **never** use the production database.

- **Always use the test DB and fixtures.** The root test config (`backend/tests/conftest.py`) sets `TESTING=true` and `TESTING_DATABASE_URL=sqlite:///:memory:` before any app imports. The app reads the database URL from env, so tests use an in-memory SQLite DB.
- **No manual production connections or hardcoded production paths.** Do not reference `simulator.db` or any production DB path in tests. Use the `db_session` and `client` fixtures so every request in API tests uses the in-memory DB.
- **Runtime check.** When `TESTING=true`, the database module raises a clear `RuntimeError` if the URL looks like production (e.g. contains `simulator.db`), so tests cannot run against production by mistake.

## Test maintenance

When you change code, keep tests in sync:

- **API endpoints:** Ensure there is a corresponding API or regression test; run the quick suite (`make test-quick` from `backend/`) after changes.
- **Models / DB:** Update fixtures in `conftest.py` and any tests that use those models; run the full suite.
- **CRUD / services:** Update unit tests for the affected module; check cascade/delete behaviour.
- **Schemas / validation:** Update example payloads in API tests and any validation tests.
- **New features:** Add regression or unit tests as appropriate; extend fixtures; document in the README if needed.

**Patterns to keep:**

- **Patch where the object is used.** Patch the name in the module that uses the dependency (e.g. `patch('simulator_core.ocpp_client.start_metering_loop')`), not the module that defines it.
- **Use fixtures.** Prefer shared setup in `conftest.py` (e.g. `client`, `db_session`) over inline data so tests stay short and consistent.

## How to run tests

- **Backend (from `backend/`):**
  - `make test` — full suite
  - `make test-unit` — unit only
  - `make test-integration` — integration only
  - `make test-api` — API only
  - `make test-quick` — quick/smoke (API)
  - `make test-coverage` — full suite with coverage (terminal + `htmlcov/`)
- **Frontend (from `frontend/`):**
  - `npm run test` or `npm run test:run` — single run
  - `npm run test:watch` — watch mode
  - `npm run test:coverage` — run with coverage (`coverage/`)
- **From repo root:** `make test` runs both backend and frontend tests.

**Optional:** From `backend/`, `make test-report` runs the suite and writes a timestamped markdown report under `testing/reports/` (with a `latest.md` copy for easy access).
