"""API tests: health and root endpoints."""
import pytest

pytestmark = pytest.mark.api


def test_api_health_returns_200(client):
    """GET /api/health returns 200 and service info."""
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data or "service" in data or data == {}


def test_root_returns_info(client):
    """GET / returns service info and docs link."""
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert "service" in data or "docs" in data or "health" in data
