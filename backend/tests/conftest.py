# Set test environment before any application or db imports.
import os

os.environ["TESTING"] = "true"
os.environ["TESTING_DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from db import SessionLocal, get_db
from main import app
from models import Base
from models.charger import Charger  # noqa: F401 - register with Base
from models.evse import Evse  # noqa: F401
from models.location import Location  # noqa: F401
from models.vehicle import Vehicle  # noqa: F401
from models.vehicle_id_tag import VehicleIdTag  # noqa: F401


def _get_engine():
    """Engine used by the app (in-memory when TESTING=true)."""
    return SessionLocal.kw["bind"]


@pytest.fixture(scope="session")
def engine():
    """One in-memory engine per test run; create tables once."""
    eng = _get_engine()
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def db_session(engine):
    """Function-scoped session; each test runs in a transaction that is rolled back."""
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection)
    session.begin_nested()
    try:
        yield session
    finally:
        session.close()
        if trans.is_active:
            trans.rollback()
        connection.close()


def _override_get_db(session):
    """Return a generator that yields the given session (for dependency override)."""
    def override():
        yield session
    return override


@pytest.fixture
def client(db_session):
    """API test client; overrides get_db to use the test db_session, cleared on teardown."""
    app.dependency_overrides[get_db] = _override_get_db(db_session)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def pytest_sessionfinish(session, exitstatus):
    """Remove any temporary test DB files created during the run (e.g. under /tmp)."""
    import glob
    for pattern in ["/tmp/test_*.db", "test_*.db"]:
        for path in glob.glob(pattern):
            try:
                os.remove(path)
            except OSError:
                pass
