"""
Data models for the Drone Fleet Telemetry API.

Defines all Pydantic models for drones, telemetry, alerts, and missions
with validation and serialization capabilities.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


def _utcnow():
    return datetime.now(timezone.utc)


class DroneModel(str, Enum):
    """Supported drone models."""
    DJI_M300 = "DJI-M300"
    SKYDIO_X10 = "Skydio-X10"
    PARROT_ANAFI = "Parrot-Anafi"


class DroneStatus(str, Enum):
    """Drone operational status."""
    IDLE = "idle"
    FLYING = "flying"
    DOCKED = "docked"
    ERROR = "error"


class MissionStatus(str, Enum):
    """Mission execution status."""
    IDLE = "idle"
    EN_ROUTE = "en_route"
    ON_SITE = "on_site"
    RETURNING = "returning"
    ABORTED = "aborted"


class AlertType(str, Enum):
    """Types of alerts detected by the anomaly engine."""
    LOW_BATTERY = "low_battery"
    GPS_DEVIATION = "gps_deviation"
    SIGNAL_LOSS = "signal_loss"
    MISSION_ABORT = "mission_abort"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    WARNING = "warning"
    CRITICAL = "critical"


class UserRole(str, Enum):
    """User roles for authorization."""
    ADMIN = "admin"
    VIEWER = "viewer"


class DroneCommandType(str, Enum):
    """Drone command types."""
    LAND = "land"
    TAKE_OFF = "take_off"
    RETURN_TO_BASE = "return_to_base"
    EMERGENCY_STOP = "emergency_stop"
    PAUSE = "pause"
    RESUME = "resume"


# ============================================================================
# Base Models
# ============================================================================


class DroneBase(BaseModel):
    """Base drone model with common fields."""
    name: str = Field(..., min_length=1, max_length=100)
    model: DroneModel = Field(default=DroneModel.DJI_M300)


class TelemetryFrameBase(BaseModel):
    """Base telemetry frame with all sensor data."""
    drone_id: UUID
    timestamp: datetime
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    altitude_m: float = Field(..., ge=0, le=150)
    battery_pct: int = Field(..., ge=0, le=100)
    speed_mps: float = Field(..., ge=0, le=20)
    signal_strength: int = Field(..., ge=0, le=100)
    mission_status: MissionStatus = Field(default=MissionStatus.IDLE)


class Waypoint(BaseModel):
    """GPS waypoint for mission planning."""
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class AlertBase(BaseModel):
    """Base alert model."""
    drone_id: UUID
    type: AlertType
    severity: AlertSeverity
    message: str


class UserBase(BaseModel):
    """Base user model."""
    username: str = Field(..., min_length=3, max_length=50)
    role: UserRole = Field(default=UserRole.VIEWER)


# ============================================================================
# Create/Input Models
# ============================================================================


class DroneCreate(DroneBase):
    """Model for creating a new drone."""
    pass


class MissionCreate(BaseModel):
    """Model for creating a new mission."""
    drone_id: UUID
    waypoints: List[Waypoint] = Field(..., min_length=1)


class UserCreate(UserBase):
    """Model for creating a new user."""
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    """Model for user login."""
    username: str
    password: str


class DroneCommand(BaseModel):
    """Model for sending commands to a drone."""
    command: DroneCommandType
    parameters: Optional[dict] = None


# ============================================================================
# Response Models
# ============================================================================


class Drone(DroneBase):
    """Complete drone model with all fields."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    status: DroneStatus = Field(default=DroneStatus.IDLE)
    mission_id: Optional[UUID] = None
    registered_at: datetime = Field(default_factory=_utcnow)


class TelemetryFrame(TelemetryFrameBase):
    """Complete telemetry frame model."""
    model_config = ConfigDict(from_attributes=True)
    
    pass


class Alert(AlertBase):
    """Complete alert model."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=_utcnow)


class Mission(BaseModel):
    """Complete mission model."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    drone_id: UUID
    waypoints: List[Waypoint]
    status: MissionStatus = Field(default=MissionStatus.IDLE)
    created_at: datetime = Field(default_factory=_utcnow)


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    """JWT token payload data."""
    user_id: UUID
    username: str
    role: UserRole


class User(UserBase):
    """Complete user model."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=_utcnow)


# ============================================================================
# Fleet Summary Models
# ============================================================================


class FleetSummary(BaseModel):
    """Aggregated fleet statistics."""
    total_drones: int
    active_drones: int
    idle_drones: int
    docked_drones: int
    error_drones: int
    average_battery_pct: float
    active_missions: int
    recent_alerts_count: int


class DroneStatusSnapshot(BaseModel):
    """Latest status snapshot for a drone."""
    drone: Drone
    telemetry: Optional[TelemetryFrame] = None
    last_update: datetime = Field(default_factory=_utcnow)


# ============================================================================
# WebSocket Message Models
# ============================================================================


class WSMessageType(str, Enum):
    """WebSocket message types."""
    SNAPSHOT = "snapshot"
    TELEMETRY = "telemetry"
    ALERT = "alert"
    STATUS_CHANGE = "status_change"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


class WSMessage(BaseModel):
    """Generic WebSocket message wrapper."""
    type: WSMessageType
    data: dict
    timestamp: datetime = Field(default_factory=_utcnow)


class WSSubscribeMessage(BaseModel):
    """Client subscription message for filtering drones."""
    subscribe: Optional[List[str]] = None  # List of drone IDs to subscribe to
    unsubscribe: Optional[List[str]] = None  # List of drone IDs to unsubscribe from


# ============================================================================
# Pagination Models
# ============================================================================


class PaginatedAlerts(BaseModel):
    """Paginated alert response."""
    items: List[Alert]
    total: int
    page: int
    page_size: int
    pages: int


class AlertQueryParams(BaseModel):
    """Query parameters for filtering alerts."""
    drone_id: Optional[UUID] = None
    severity: Optional[AlertSeverity] = None
    alert_type: Optional[AlertType] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
