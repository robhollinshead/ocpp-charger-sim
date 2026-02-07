"""Database engine and session for SQLite (dev) / PostgreSQL (prod)."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from utils.config import DATABASE_URL

_engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a DB session and close after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
