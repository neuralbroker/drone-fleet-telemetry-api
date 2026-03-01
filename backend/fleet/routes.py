"""
Fleet routes for the Drone Fleet Telemetry API.

Provides REST endpoints for fleet management, missions, and alerts.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query

from backend.fleet.models import (
    Drone, DroneCreate, TelemetryFrame,
    Mission, MissionCreate,
    Alert, AlertSeverity,
    FleetSummary, PaginatedAlerts
)
from backend.fleet.service import fleet_service, get_fleet_service
from backend.auth.routes import get_current_user, TokenData, UserRole

logger = logging.getLogger(__name__)

# Router
router = APIRouter(prefix="/fleet", tags=["Fleet Management"])


@router.get("", response_model=list[Drone])
async def list_drones(
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service)
):
    """
    List all drones in the fleet.
    
    Requires authentication.
    
    Returns:
        List of all registered drones
    """
    return service.list_drones()


@router.post("", response_model=Drone, status_code=status.HTTP_201_CREATED)
async def register_drone(
    drone_create: DroneCreate,
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service)
):
    """
    Register a new drone in the fleet.
    
    Requires admin role.
    
    Returns:
        Created drone
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to register drones"
        )
    
    return service.register_drone(drone_create)


# NOTE: /summary must come BEFORE /{drone_id} to avoid route conflict
@router.get("/summary", response_model=FleetSummary)
async def get_fleet_summary(
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service)
):
    """
    Get aggregated fleet statistics.
    
    Requires authentication.
    
    Returns:
        Fleet summary with counts and averages
    """
    return service.get_fleet_summary()


@router.get("/{drone_id}", response_model=Drone)
async def get_drone(
    drone_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service)
):
    """
    Get detailed information about a specific drone.
    
    Requires authentication.
    
    Returns:
        Drone details
    """
    drone = service.get_drone(drone_id)
    if not drone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Drone not found"
        )
    
    return drone


@router.get("/{drone_id}/status")
async def get_drone_status(
    drone_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service)
):
    """
    Get latest telemetry snapshot for a drone.
    
    Requires authentication.
    
    Returns:
        Drone info with latest telemetry
    """
    drone = service.get_drone(drone_id)
    if not drone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Drone not found"
        )
    
    telemetry = service.get_drone_telemetry(drone_id)
    
    return {
        "drone": drone,
        "telemetry": telemetry
    }


# Mission routes
missions_router = APIRouter(prefix="/missions", tags=["Missions"])


@missions_router.post("", response_model=Mission, status_code=status.HTTP_201_CREATED)
async def create_mission(
    mission_create: MissionCreate,
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service)
):
    """
    Create and assign a mission to a drone.
    
    Requires admin role.
    
    Returns:
        Created mission
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to create missions"
        )
    
    mission = service.create_mission(mission_create)
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Drone not found"
        )
    
    return mission


@missions_router.get("/{mission_id}", response_model=Mission)
async def get_mission(
    mission_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service)
):
    """
    Get mission details.
    
    Requires authentication.
    
    Returns:
        Mission details
    """
    mission = service.get_mission(mission_id)
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission not found"
        )
    
    return mission


@missions_router.post("/{mission_id}/abort", response_model=Mission)
async def abort_mission(
    mission_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service)
):
    """
    Abort an active mission.
    
    Requires admin role.
    
    Returns:
        Updated mission with aborted status
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to abort missions"
        )
    
    mission = await service.abort_mission(mission_id)
    if not mission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mission not found"
        )
    
    return mission


# Alert routes
alerts_router = APIRouter(prefix="/alerts", tags=["Alerts"])


@alerts_router.get("", response_model=list[Alert])
async def list_alerts(
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service),
    drone_id: Optional[UUID] = Query(None, description="Filter by drone ID"),
    severity: Optional[AlertSeverity] = Query(None, description="Filter by severity"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of alerts")
):
    """
    List recent alerts, optionally filtered.
    
    Requires authentication.
    
    Returns:
        List of alerts
    """
    return service.get_alerts(drone_id=drone_id, severity=severity, limit=limit)


@alerts_router.get("/{drone_id}", response_model=list[Alert])
async def get_drone_alerts(
    drone_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    service = Depends(get_fleet_service),
    limit: int = Query(50, ge=1, le=100)
):
    """
    Get alerts for a specific drone.
    
    Requires authentication.
    
    Returns:
        List of alerts for the drone
    """
    return service.get_alerts(drone_id=drone_id, limit=limit)
