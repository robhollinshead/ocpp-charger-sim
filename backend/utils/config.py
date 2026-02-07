"""Configuration from environment."""
import os

PORT = int(os.environ.get("PORT", "8001"))
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./simulator.db",
)
