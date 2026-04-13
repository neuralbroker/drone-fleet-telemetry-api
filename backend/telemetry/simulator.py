"""
Telemetry simulator for the Drone Fleet Telemetry API.

Simulates a fleet of autonomous drones streaming live telemetry data.
Each drone runs as an async background task that generates realistic
telemetry frames based on mission state and environmental factors.
"""
import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, Awaitable, Any
from uuid import UUID

from backend.config import settings
from backend.fleet.models import (
    Drone, DroneModel, DroneStatus, TelemetryFrame, MissionStatus
)

logger = logging.getLogger(__name__)


# Default starting coordinates (Pune, India)
DEFAULT_LAT = 18.5204
DEFAULT_LNG = 73.8567

# Simulation parameters
GPS_DRIFT_RANGE = 0.0005
BATTERY_DRAIN_FLYING = 0.05  # % per second
BATTERY_DRAIN_IDLE = 0.01    # % per second
ALTITUDE_MIN_FLIGHT = 30.0
ALTITUDE_MAX_FLIGHT = 90.0
SPEED_MIN = 5.0
SPEED_MAX = 12.0
SIGNAL_DROP_CHANCE = 0.02   # 2% chance to drop signal
LOW_SIGNAL_THRESHOLD = 25

# Battery thresholds
BATTERY_RETURN_THRESHOLD = 20
BATTERY_CRITICAL_THRESHOLD = 5


class DroneSimulator:
    """
    Simulates a single drone with realistic telemetry behavior.
    
    Generates telemetry frames based on drone state, mission status,
    and simulates battery drain, GPS drift, and signal degradation.
    """
    
    def __init__(
        self,
        drone_id: UUID,
        name: str,
        model: DroneModel,
        on_telemetry: Optional[Callable[[TelemetryFrame], Awaitable[None]]] = None,
        on_status_change: Optional[Callable[[DroneStatus], Awaitable[None]]] = None
    ):
        """
        Initialize drone simulator.
        
        Args:
            drone_id: Unique drone identifier
            name: Human-readable drone name
            model: Drone model type
            on_telemetry: Callback for telemetry frame events
            on_status_change: Callback for status change events
        """
        self.drone_id = drone_id
        self.name = name
        self.model = model
        
        # Callbacks
        self.on_telemetry = on_telemetry
        self.on_status_change = on_status_change
        
        # State
        self.status = DroneStatus.IDLE
        self.battery_pct = 100.0
        self.lat = DEFAULT_LAT + random.uniform(-0.01, 0.01)
        self.lng = DEFAULT_LNG + random.uniform(-0.01, 0.01)
        self.altitude_m = 0.0
        self.speed_mps = 0.0
        self.signal_strength = random.randint(70, 100)
        self.mission_status = MissionStatus.IDLE
        self.mission_id: Optional[UUID] = None
        self.waypoints: list = []
        self.current_waypoint_index = 0
        
        # Previous position for GPS deviation calculation
        self._prev_lat = self.lat
        self._prev_lng = self.lng
        self._prev_timestamp = datetime.now(timezone.utc)
        
        # Task management
        self._task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(f"Initialized drone simulator: {name} ({drone_id})")
    
    @property
    def is_running(self) -> bool:
        """Check if simulator is running."""
        return bool(self._running and self._task and self._task.done() is False)
    
    async def start(self) -> None:
        """Start the drone simulation loop."""
        if self._running:
            logger.warning(f"Drone {self.name} already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"Started drone simulator: {self.name}")
    
    async def stop(self) -> None:
        """Stop the drone simulation loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped drone simulator: {self.name}")
    
    async def set_mission(
        self,
        mission_id: UUID,
        waypoints: list,
        status: MissionStatus = MissionStatus.EN_ROUTE
    ) -> None:
        """
        Assign a mission to the drone.
        
        Args:
            mission_id: Mission identifier
            waypoints: List of waypoints to traverse
            status: Initial mission status
        """
        self.mission_id = mission_id
        self.waypoints = waypoints
        self.current_waypoint_index = 0
        self.mission_status = status
        
        # Set to flying if we have waypoints
        if status != MissionStatus.IDLE and self.status != DroneStatus.DOCKED:
            self.status = DroneStatus.FLYING
        
        logger.info(f"Drone {self.name} assigned mission {mission_id}")
    
    async def abort_mission(self) -> None:
        """Abort the current mission."""
        self.mission_status = MissionStatus.ABORTED
        self.status = DroneStatus.IDLE
        self.speed_mps = 0.0
        self.altitude_m = 0.0
        self.waypoints = []
        self.current_waypoint_index = 0
        logger.info(f"Drone {self.name} mission aborted")
        
        if self.on_status_change:
            await self.on_status_change(self.status)
    
    async def _run(self) -> None:
        """Main simulation loop - runs until stopped."""
        while self._running:
            try:
                # Generate telemetry frame
                frame = await self._generate_telemetry()
                
                # Emit telemetry
                if self.on_telemetry:
                    await self.on_telemetry(frame)
                
                # Wait for next tick
                await asyncio.sleep(settings.SIMULATOR_TELEMETRY_INTERVAL)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in drone {self.name} simulation: {e}")
                # Continue running despite errors
                await asyncio.sleep(settings.SIMULATOR_TELEMETRY_INTERVAL)
    
    async def _generate_telemetry(self) -> TelemetryFrame:
        """
        Generate a single telemetry frame with realistic values.
        
        Updates internal state based on:
        - Battery drain (varies by status)
        - GPS drift when moving
        - Random signal drops
        - Mission waypoint progression
        
        Returns:
            TelemetryFrame with current drone state
        """
        now = datetime.now(timezone.utc)
        
        # Calculate GPS movement for deviation detection
        time_delta = (now - self._prev_timestamp).total_seconds()
        
        # Update state based on status
        await self._update_state(time_delta)
        
        # Calculate GPS deviation
        lat_diff = abs(self.lat - self._prev_lat)
        lng_diff = abs(self.lng - self._prev_lng)
        gps_deviation = max(lat_diff, lng_diff) / max(time_delta, 0.001)
        
        # Create telemetry frame
        frame = TelemetryFrame(
            drone_id=self.drone_id,
            timestamp=now,
            lat=self.lat,
            lng=self.lng,
            altitude_m=self.altitude_m,
            battery_pct=int(self.battery_pct),
            speed_mps=round(self.speed_mps, 2),
            signal_strength=self.signal_strength,
            mission_status=self.mission_status
        )
        
        # Store for next iteration
        self._prev_lat = self.lat
        self._prev_lng = self.lng
        self._prev_timestamp = now
        
        return frame
    
    async def _update_state(self, time_delta: float) -> None:
        """
        Update drone state based on current status and mission.
        
        Args:
            time_delta: Time since last update in seconds
        """
        # Battery drain based on status
        if self.status == DroneStatus.FLYING:
            self.battery_pct -= BATTERY_DRAIN_FLYING * time_delta
        elif self.status == DroneStatus.IDLE:
            self.battery_pct -= BATTERY_DRAIN_IDLE * time_delta
        # Docked drones don't drain
        
        # Clamp battery
        self.battery_pct = max(0.0, min(100.0, self.battery_pct))
        
        # Check battery thresholds
        if self.battery_pct <= BATTERY_CRITICAL_THRESHOLD:
            # Critical - abort mission
            if self.mission_status not in [MissionStatus.IDLE, MissionStatus.ABORTED]:
                await self.abort_mission()
                self.status = DroneStatus.ERROR
        elif self.battery_pct <= BATTERY_RETURN_THRESHOLD:
            # Return to base
            if self.mission_status == MissionStatus.EN_ROUTE:
                self.mission_status = MissionStatus.RETURNING
        
        # GPS drift when flying
        if self.status == DroneStatus.FLYING:
            self.lat += random.uniform(-GPS_DRIFT_RANGE, GPS_DRIFT_RANGE)
            self.lng += random.uniform(-GPS_DRIFT_RANGE, GPS_DRIFT_RANGE)
            
            # Clamp to valid ranges
            self.lat = max(-90, min(90, self.lat))
            self.lng = max(-180, min(180, self.lng))
            
            # Altitude random walk
            if self.altitude_m > 0:
                self.altitude_m += random.uniform(-2, 2)
                self.altitude_m = max(ALTITUDE_MIN_FLIGHT, min(ALTITUDE_MAX_FLIGHT, self.altitude_m))
            else:
                self.altitude_m = random.uniform(ALTITUDE_MIN_FLIGHT, ALTITUDE_MAX_FLIGHT)
            
            # Speed based on mission status
            if self.mission_status in [MissionStatus.EN_ROUTE, MissionStatus.ON_SITE]:
                self.speed_mps = random.uniform(SPEED_MIN, SPEED_MAX)
            elif self.mission_status == MissionStatus.RETURNING:
                self.speed_mps = random.uniform(SPEED_MIN * 0.7, SPEED_MAX * 0.7)
            else:
                self.speed_mps = 0.0
            
            # Progress through waypoints
            if self.waypoints and self.mission_status == MissionStatus.EN_ROUTE:
                distance = self._distance_to_waypoint()
                if distance < 0.01:  # Close to waypoint
                    self.current_waypoint_index += 1
                    if self.current_waypoint_index >= len(self.waypoints):
                        self.mission_status = MissionStatus.ON_SITE
        
        # Signal strength degradation
        if random.random() < SIGNAL_DROP_CHANCE:
            self.signal_strength = random.randint(20, 30)
        else:
            # Gradually recover signal
            self.signal_strength = min(100, self.signal_strength + random.randint(0, 5))
        
        # Status based on battery and mission
        if self.battery_pct <= 0:
            self.status = DroneStatus.DOCKED
            self.altitude_m = 0.0
            self.speed_mps = 0.0
    
    def _distance_to_waypoint(self) -> float:
        """Calculate distance to current waypoint (simplified)."""
        if not self.waypoints or self.current_waypoint_index >= len(self.waypoints):
            return float('inf')
        
        wp = self.waypoints[self.current_waypoint_index]
        # Simplified Euclidean distance
        return ((self.lat - wp['lat'])**2 + (self.lng - wp['lng'])**2)**0.5


class TelemetrySimulator:
    """
    Manages a fleet of drone simulators.
    
    Handles startup/shutdown of multiple drones and provides
    a central interface for the telemetry system.
    """
    
    def __init__(self):
        """Initialize the telemetry simulator."""
        self.drones: Dict[UUID, DroneSimulator] = {}
        self._running = False
        
        # Callbacks for external systems
        self.on_telemetry: Optional[Callable[[TelemetryFrame], Awaitable[None]]] = None
        self.on_drone_status_change: Optional[Callable[[UUID, DroneStatus], Awaitable[None]]] = None
    
    @property
    def is_running(self) -> bool:
        """Check if simulator is running."""
        return self._running
    
    async def start(self, drone_count: Optional[int] = None) -> None:
        """
        Start the simulator with specified number of drones.
        
        Args:
            drone_count: Number of drones to spawn (default from config)
        """
        if self._running:
            logger.warning("Telemetry simulator already running")
            return
        
        count = drone_count or settings.SIMULATOR_DRONES_COUNT
        
        # Create drones
        drone_names = [
            "Falcon-1", "Eagle-2", "Hawk-3", "Phoenix-4", "Condor-5",
            "Raptor-6", "Osprey-7", "Kestrel-8", "Merlin-9", "Griffin-10"
        ]
        
        models = list(DroneModel)
        
        for i in range(count):
            drone_id = UUID(f"00000000-0000-4000-8000-{(i+1):012d}")
            name = drone_names[i % len(drone_names)]
            model = models[i % len(models)]
            
            simulator = DroneSimulator(
                drone_id=drone_id,
                name=name,
                model=model,
                on_telemetry=self._handle_telemetry,
                on_status_change=lambda s, did=drone_id: self._handle_status_change(did, s)
            )
            
            self.drones[drone_id] = simulator
            await simulator.start()
        
        self._running = True
        logger.info(f"Started telemetry simulator with {count} drones")
    
    async def stop(self) -> None:
        """Stop all drone simulators."""
        self._running = False
        
        for drone_id, simulator in self.drones.items():
            await simulator.stop()
        
        self.drones.clear()
        logger.info("Stopped telemetry simulator")
    
    async def _handle_telemetry(self, frame: TelemetryFrame) -> None:
        """
        Handle incoming telemetry frame from a drone.
        
        Args:
            frame: Telemetry frame from drone
        """
        # Forward to external callback if set
        if self.on_telemetry:
            try:
                await self.on_telemetry(frame)
            except Exception as e:
                logger.error(f"Error in telemetry callback: {e}")
    
    async def _handle_status_change(self, drone_id: UUID, status: DroneStatus) -> None:
        """
        Handle drone status change.
        
        Args:
            drone_id: Drone identifier
            status: New status
        """
        if self.on_drone_status_change:
            try:
                await self.on_drone_status_change(drone_id, status)
            except Exception as e:
                logger.error(f"Error in status change callback: {e}")
    
    def get_drone(self, drone_id: UUID) -> Optional[DroneSimulator]:
        """Get simulator for specific drone."""
        return self.drones.get(drone_id)
    
    def get_all_drones(self) -> Dict[UUID, DroneSimulator]:
        """Get all drone simulators."""
        return self.drones.copy()
    
    def get_drone_info(self, drone_id: UUID) -> Optional[Drone]:
        """Get drone info for API responses."""
        simulator = self.drones.get(drone_id)
        if not simulator:
            return None
        
        return Drone(
            id=simulator.drone_id,
            name=simulator.name,
            model=simulator.model,
            status=simulator.status,
            mission_id=simulator.mission_id
        )


# Global simulator instance
simulator = TelemetrySimulator()


async def get_simulator() -> TelemetrySimulator:
    """Get the global telemetry simulator instance."""
    return simulator
