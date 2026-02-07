"""OCPP Charger Simulator — FastAPI backend."""
import logging
import os
import subprocess
import sys

from fastapi import FastAPI

# Show OCPP incoming/outgoing messages and simulator warnings (INFO level)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("simulator_core").setLevel(logging.INFO)
from fastapi.middleware.cors import CORSMiddleware

from db import SessionLocal
from api.chargers import router as chargers_router
from api.locations import router as locations_router
from api.routes import router
from repositories.charger_repository import (
    list_all_chargers as repo_list_all_chargers,
    list_evses_by_charger_id as repo_list_evses_by_charger_id,
)
from repositories.location_repository import count_locations, create_location as repo_create_location
from schemas.health import HealthResponse
from simulator_core.charger import Charger as SimCharger
from simulator_core.evse import EVSE
from simulator_core.store import add as store_add, seed_default

app = FastAPI(
    title="OCPP Charger Simulator",
    description="Standalone OCPP 1.6J charger simulator backend",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes under /api (no static mount at / so /api is never shadowed)
app.include_router(router, prefix="/api")
app.include_router(locations_router, prefix="/api")
app.include_router(chargers_router, prefix="/api")


@app.get("/api/health", response_model=HealthResponse)
def api_health() -> HealthResponse:
    """Explicit health route so /api/health is always available."""
    return HealthResponse()


@app.on_event("startup")
def startup() -> None:
    """Run DB migrations and seed default charger."""
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic upgrade failed: {result.stderr or result.stdout}")
    _seed_locations_if_empty()
    _load_chargers_from_db()


def _load_chargers_from_db() -> None:
    """Load chargers from DB into simulator store. Fall back to seed_default if none exist."""
    db = SessionLocal()
    try:
        rows = repo_list_all_chargers(db)
        if not rows:
            seed_default()
            return
        for row in rows:
            evse_rows = repo_list_evses_by_charger_id(db, row.id)
            if not evse_rows:
                evses = [EVSE(evse_id=1, max_power_W=22000.0, voltage_V=230.0)]
            else:
                evses = [
                    EVSE(evse_id=e.evse_id, max_power_W=22000.0, voltage_V=230.0)
                    for e in evse_rows
                ]
            sim = SimCharger(
                charge_point_id=row.charge_point_id,
                evses=evses,
                csms_url=row.connection_url,
                config={"meter_interval_s": 10.0, "voltage_V": 230.0},
                location_id=row.location_id,
                charger_name=row.charger_name,
                ocpp_version=row.ocpp_version,
            )
            store_add(sim)
    finally:
        db.close()


def _seed_locations_if_empty() -> None:
    """Seed loc-1 and loc-2 so frontend mock chargers have valid locations."""
    db = SessionLocal()
    try:
        if count_locations(db) > 0:
            return
        repo_create_location(db, "Downtown Parking Garage", "123 Main St, City Center", "loc-1")
        repo_create_location(db, "Mall Shopping Center", "456 Commerce Blvd", "loc-2")
    finally:
        db.close()


@app.get("/")
def root() -> dict:
    """Root redirect/info."""
    return {"service": "ocpp-simulator", "docs": "/docs", "health": "/api/health"}
