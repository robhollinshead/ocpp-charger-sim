"""Configuration from environment."""
import os

PORT = int(os.environ.get("PORT", "8001"))

# When TESTING=true, use test DB URL so tests never touch production.
if os.environ.get("TESTING") == "true":
    DATABASE_URL = os.environ.get("TESTING_DATABASE_URL", "sqlite:///:memory:")
else:
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "sqlite:///./simulator.db",
    )
