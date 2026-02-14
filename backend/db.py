"""Database engine and session for SQLite (dev) / PostgreSQL (prod)."""
from collections.abc import Generator
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from utils.config import DATABASE_URL

# Runtime safety: when TESTING=true, never use production DB.
if os.environ.get("TESTING") == "true":
    url = DATABASE_URL
    if "simulator.db" in url or (":memory:" not in url and "test" not in url.lower().split("?")[0]):
        raise RuntimeError(
            "Tests must not run against production. Set TESTING_DATABASE_URL to sqlite:///:memory: "
            "(or another test URL containing :memory: or 'test')."
        )

_connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
# In-memory SQLite: use one connection so all sessions share the same DB.
_engine_kw = {"connect_args": _connect_args, "echo": False}
if "sqlite" in DATABASE_URL and ":memory:" in DATABASE_URL:
    _engine_kw["poolclass"] = StaticPool

_engine = create_engine(DATABASE_URL, **_engine_kw)

# Enable foreign keys for SQLite so FK behaviour is consistent.
if "sqlite" in DATABASE_URL:

    @event.listens_for(_engine, "connect")
    def _sqlite_fk(dbapi_conn, connection_record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a DB session and close after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
