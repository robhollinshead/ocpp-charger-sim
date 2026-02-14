"""Integration tests: location repository with test DB session."""
import pytest

from repositories.location_repository import (
    count_locations,
    create_location,
    delete_location,
    get_location,
    list_locations,
)

pytestmark = pytest.mark.integration


def test_create_and_list_locations(db_session):
    """Create locations and list them via repository (DB + repository together)."""
    create_location(db_session, "Site A", "1 Test St", "loc-a")
    create_location(db_session, "Site B", "2 Test St", "loc-b")
    names = [loc.name for loc in list_locations(db_session)]
    assert "Site A" in names and "Site B" in names
    assert count_locations(db_session) >= 2


def test_get_and_delete_location(db_session):
    """Get location by id and delete (integration)."""
    create_location(db_session, "To Delete", "99 Nowhere", "loc-del")
    loc = get_location(db_session, "loc-del")
    assert loc is not None
    assert loc.name == "To Delete"
    assert delete_location(db_session, "loc-del") is True
    assert get_location(db_session, "loc-del") is None
