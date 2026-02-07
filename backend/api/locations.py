"""Location API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from repositories.charger_repository import count_chargers_by_location
from repositories.location_repository import create_location as repo_create_location
from repositories.location_repository import delete_location as repo_delete_location
from repositories.location_repository import list_locations as repo_list_locations
from schemas.locations import LocationCreate, LocationResponse
from simulator_core.store import remove_by_location_id

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationResponse])
def list_locations(db: Session = Depends(get_db)) -> list[LocationResponse]:
    """List all locations."""
    locations = repo_list_locations(db)
    return [
        LocationResponse(
            id=loc.id,
            name=loc.name,
            address=loc.address,
            charger_count=count_chargers_by_location(db, loc.id),
        )
        for loc in locations
    ]


@router.post("", response_model=LocationResponse, status_code=status.HTTP_201_CREATED)
def create_location(
    body: LocationCreate,
    db: Session = Depends(get_db),
) -> LocationResponse:
    """Create a new location."""
    loc = repo_create_location(db, name=body.name, address=body.address)
    return LocationResponse(
        id=loc.id,
        name=loc.name,
        address=loc.address,
        charger_count=count_chargers_by_location(db, loc.id),
    )


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(location_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a location by id. Also removes all chargers associated with this location."""
    remove_by_location_id(location_id)
    if not repo_delete_location(db, location_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
