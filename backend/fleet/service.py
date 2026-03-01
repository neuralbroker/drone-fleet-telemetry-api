"""
Fleet service for the Drone Fleet Telemetry API.

Provides business logic for managing drones, missions, and alerts.
Interfaces with the simulator and Redis storage.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from backend.fleet.models import (
    Drone, DroneCreate, DroneStatus, TelemetryFrame,
    Mission, MissionCreate, MissionStatus,
    Alert, AlertType, AlertSeverity,
    FleetSummary
)
from backend.telemetry.simulator import simulator

logger = logging.getLogger(__name__)


class FleetService:
    """
    Fleet management service.
    
    Manages drone registry, missions, and provides aggregated fleet data.
    """
    
    def __init__(self):
        """Initialize fleet service."""
        self._drones: Dict[UUID, Drone] = {}
        self._missions: Dict[UUID, Mission] = {}
        self._alerts: List[Alert] = []
        self._telemetry_cache: Dict[UUID, TelemetryFrame] = {}
    
    async def initialize(self) -> None:
        """Initialize the fleet service with simulated drones."""
        # Get drones from simulator
        sim_drones = simulator.get_all_drones()
        
        for drone_id, sim in sim_drones.items():
            drone = Drone(
                id=drone_id,
                name=sim.name,
                model=sim.model,
                status=sim.status,
                mission_id=sim.mission_id
            )
            self._drones[drone_id] = drone
        
        logger.info(f"Fleet service initialized with {len(self._drones)} drones")
    
    def register_drone(self, drone_create: DroneCreate) -> Drone:
        """
        Register a new drone.
        
        Args:
            drone_create: Drone creation data
            
        Returns:
            Created drone
        """
        drone_id = uuid4()
        drone = Drone(
            id=drone_id,
            name=drone_create.name,
            model=drone_create.model,
            status=DroneStatus.IDLE
        )
        
        self._drones[drone_id] = drone
        logger.info(f"Registered new drone: {drone.name} ({drone_id})")
        
        return drone
    
    def get_drone(self, drone_id: UUID) -> Optional[Drone]:
        """Get drone by ID."""
        return self._drones.get(drone_id)
    
    def list_drones(self) -> List[Drone]:
        """Get all drones."""
        return list(self._drones.values())
    
    async def update_drone_status(self, drone_id: UUID) -> None:
        """
        Update drone status from simulator.
        
        Args:
            drone_id: Drone identifier
        """
        sim = simulator.get_drone(drone_id)
        if sim and drone_id in self._drones:
            self._drones[drone_id].status = sim.status
            self._drones[drone_id].mission_id = sim.mission_id
    
    def get_drone_telemetry(self, drone_id: UUID) -> Optional[TelemetryFrame]:
        """
        Get latest telemetry for a drone.
        
        Args:
            drone_id: Drone identifier
            
        Returns:
            Latest telemetry frame or None
        """
        return self._telemetry_cache.get(drone_id)
    
    def update_telemetry(self, frame: TelemetryFrame) -> None:
        """
        Update cached telemetry for a drone.
        
        Args:
            frame: New telemetry frame
        """
        self._telemetry_cache[frame.drone_id] = frame
        
        # Update drone status from telemetry
        if frame.drone_id in self._drones:
            drone = self._drones[frame.drone_id]
            
            # Map mission status to drone status
            if frame.mission_status == MissionStatus.ABORTED:
                drone.status = DroneStatus.ERROR
            elif frame.mission_status in [MissionStatus.EN_ROUTE, MissionStatus.ON_SITE]:
                drone.status = DroneStatus.FLYING
            elif frame.battery_pct <= 0:
                drone.status = DroneStatus.DOCKED
    
    def create_mission(self, mission_create: MissionCreate) -> Optional[Mission]:
        """
        Create and assign a mission to a drone.
        
        Args:
            mission_create: Mission creation data
            
        Returns:
            Created mission or None if drone not found
        """
        drone_id = mission_create.drone_id
        
        # Check drone exists
        if drone_id not in self._drones:
            return None
        
        # Create mission - keep waypoints as Waypoint objects
        mission = Mission(
            id=uuid4(),
            drone_id=drone_id,
            waypoints=mission_create.waypoints,
            status=MissionStatus.EN_ROUTE
        )
        
        self._missions[mission.id] = mission
        
        # Assign to simulator (schedule async task)
        sim = simulator.get_drone(drone_id)
        if sim:
            asyncio.create_task(sim.set_mission(
                mission.id,
                [wp.model_dump() for wp in mission_create.waypoints],
                MissionStatus.EN_ROUTE
            ))
        
        logger.info(f"Created mission {mission.id} for drone {drone_id}")
        
        return mission
    
    def get_mission(self, mission_id: UUID) -> Optional[Mission]:
        """Get mission by ID."""
        return self._missions.get(mission_id)
    
    async def abort_mission(self, mission_id: UUID) -> Optional[Mission]:
        """
        Abort an active mission.
        
        Args:
            mission_id: Mission to abort
            
        Returns:
            Updated mission or None if not found
        """
        mission = self._missions.get(mission_id)
        if not mission:
            return None
        
        mission.status = MissionStatus.ABORTED
        
        # Tell simulator to abort
        sim = simulator.get_drone(mission.drone_id)
        if sim:
            await sim.abort_mission()
        
        # Create alert
        alert = Alert(
            drone_id=mission.drone_id,
            type=AlertType.MISSION_ABORT,
            severity=AlertSeverity.CRITICAL,
            message=f"Mission {mission_id} aborted"
        )
        self.add_alert(alert)
        
        logger.info(f"Aborted mission {mission_id}")
        
        return mission
    
    def add_alert(self, alert: Alert) -> None:
        """
        Add an alert to the system.
        
        Args:
            alert: Alert to add
        """
        self._alerts.insert(0, alert)  # Newest first
        
        # Keep only last 100 alerts per drone
        drone_alerts = [a for a in self._alerts if a.drone_id == alert.drone_id]
        if len(drone_alerts) > 100:
            # Remove oldest alerts for this drone
            old_ids = {a.id for a in drone_alerts[100:]}
            self._alerts = [a for a in self._alerts if a.id not in old_ids]
        
        logger.debug(f"Alert added: {alert.type} for drone {alert.drone_id}")
    
    def get_alerts(
        self,
        drone_id: Optional[UUID] = None,
        severity: Optional[AlertSeverity] = None,
        limit: int = 50
    ) -> List[Alert]:
        """
        Get alerts, optionally filtered.
        
        Args:
            drone_id: Filter by drone
            severity: Filter by severity
            limit: Maximum number of alerts
            
        Returns:
            List of alerts
        """
        alerts = self._alerts
        
        if drone_id:
            alerts = [a for a in alerts if a.drone_id == drone_id]
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        return alerts[:limit]
    
    def get_fleet_summary(self) -> FleetSummary:
        """
        Get aggregated fleet statistics.
        
        Returns:
            Fleet summary
        """
        drones = list(self._drones.values())
        total = len(drones)
        
        active = sum(1 for d in drones if d.status == DroneStatus.FLYING)
        idle = sum(1 for d in drones if d.status == DroneStatus.IDLE)
        docked = sum(1 for d in drones if d.status == DroneStatus.DOCKED)
        error = sum(1 for d in drones if d.status == DroneStatus.ERROR)
        
        # Calculate average battery
        battery_values = [
            self._telemetry_cache[d.id].battery_pct
            for d in drones
            if d.id in self._telemetry_cache
        ]
        avg_battery = sum(battery_values) / len(battery_values) if battery_values else 0.0
        
        # Count active missions
        active_missions = sum(
            1 for m in self._missions.values()
            if m.status in [MissionStatus.EN_ROUTE, MissionStatus.ON_SITE]
        )
        
        # Recent alerts (last hour)
        recent_alerts = sum(1 for a in self._alerts if (datetime.utcnow() - a.timestamp).total_seconds() < 3600)
        
        return FleetSummary(
            total_drones=total,
            active_drones=active,
            idle_drones=idle,
            docked_drones=docked,
            error_drones=error,
            average_battery_pct=round(avg_battery, 2),
            active_missions=active_missions,
            recent_alerts_count=recent_alerts
        )


# Global service instance
fleet_service = FleetService()


async def get_fleet_service() -> FleetService:
    """Get the global fleet service instance."""
    return fleet_service
