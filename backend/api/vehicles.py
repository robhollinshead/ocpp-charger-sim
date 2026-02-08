"""Vehicle API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import get_db
from repositories.location_repository import get_location
from repositories.vehicle_repository import (
    create_vehicle as repo_create_vehicle,
    delete_vehicle as repo_delete_vehicle,
    get_vehicle_by_id as repo_get_vehicle_by_id,
    get_vehicle_by_id_tag as repo_get_vehicle_by_id_tag,
    get_vehicle_by_name as repo_get_vehicle_by_name,
    list_vehicles_by_location as repo_list_vehicles_by_location,
)
from schemas.vehicles import VehicleCreate, VehicleResponse

router = APIRouter(tags=["vehicles"])


def _vehicle_to_response(v) -> VehicleResponse:
    """Build VehicleResponse from model instance."""
    return VehicleResponse(
        id=v.id,
        name=v.name,
        idTag=v.id_tag,
        battery_capacity_kWh=float(v.battery_capacity_kwh),
        location_id=v.location_id,
    )


@router.get("/locations/{location_id}/vehicles", response_model=list[VehicleResponse])
def list_vehicles(location_id: str, db: Session = Depends(get_db)) -> list[VehicleResponse]:
    """List all vehicles at a location."""
    if get_location(db, location_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    vehicles = repo_list_vehicles_by_location(db, location_id)
    return [_vehicle_to_response(v) for v in vehicles]


@router.post(
    "/locations/{location_id}/vehicles",
    response_model=VehicleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_vehicle(
    location_id: str,
    body: VehicleCreate,
    db: Session = Depends(get_db),
) -> VehicleResponse:
    """Create a new vehicle at a location."""
    if get_location(db, location_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    if repo_get_vehicle_by_name(db, body.name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Vehicle with name '{body.name}' already exists",
        )
    if repo_get_vehicle_by_id_tag(db, body.idTag) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Vehicle with idTag '{body.idTag}' already exists",
        )
    try:
        vehicle = repo_create_vehicle(
            db,
            location_id=location_id,
            name=body.name,
            id_tag=body.idTag,
            battery_capacity_kwh=body.battery_capacity_kWh,
        )
        return _vehicle_to_response(vehicle)
    except IntegrityError as e:
        if "name" in str(e) or "id_tag" in str(e) or "unique" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vehicle with that name or idTag already exists",
            ) from e
        raise


@router.delete(
    "/locations/{location_id}/vehicles/{vehicle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_vehicle(
    location_id: str,
    vehicle_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a vehicle by id. Vehicle must belong to the given location."""
    if get_location(db, location_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    vehicle = repo_get_vehicle_by_id(db, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    if vehicle.location_id != location_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    repo_delete_vehicle(db, vehicle_id)
    return None
