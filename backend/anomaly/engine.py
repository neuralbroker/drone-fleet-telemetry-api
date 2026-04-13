"""
Anomaly detection engine for the Drone Fleet Telemetry API.

Evaluates incoming telemetry frames against rule-based conditions
to detect anomalies and generate alerts. Includes optional OpenAI
integration for alert summarization.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Callable, Awaitable
from uuid import UUID, uuid4

from backend.config import settings
from backend.fleet.models import (
    TelemetryFrame, Alert, AlertType, AlertSeverity, MissionStatus
)
from backend.fleet.service import fleet_service

logger = logging.getLogger(__name__)


class AnomalyEngine:
    """
    Rule-based anomaly detection engine.
    
    Monitors telemetry frames and generates alerts when
    predefined thresholds are exceeded.
    """
    
    # Alert thresholds
    LOW_BATTERY_WARNING = 25
    LOW_BATTERY_CRITICAL = 10
    SIGNAL_LOSS_THRESHOLD = 25
    GPS_DEVIATION_THRESHOLD = 0.01  # degrees per second
    
    # Debounce map: drone_id -> {alert_type: last_alert_time}
    _last_alert: Dict[UUID, Dict[AlertType, datetime]] = {}
    
    def __init__(self):
        """Initialize anomaly engine."""
        self._on_alert_callback: Optional[Callable[[Alert], Awaitable[None]]] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the anomaly engine."""
        self._running = True
        logger.info("Anomaly detection engine started")
    
    async def stop(self) -> None:
        """Stop the anomaly engine."""
        self._running = False
        logger.info("Anomaly detection engine stopped")
    
    def set_alert_callback(
        self,
        callback: Callable[[Alert], Awaitable[None]]
    ) -> None:
        """
        Set callback for generated alerts.
        
        Args:
            callback: Async function to call with alert
        """
        self._on_alert_callback = callback
    
    async def evaluate(self, frame: TelemetryFrame) -> Optional[Alert]:
        """
        Evaluate a telemetry frame for anomalies.
        
        Checks all anomaly rules and generates appropriate alerts.
        Implements debouncing to prevent alert flooding.
        
        Args:
            frame: Telemetry frame to evaluate
            
        Returns:
            Generated alert or None
        """
        if not self._running:
            return None
        
        alert = None
        
        # Rule 1: Low Battery Warning
        if frame.battery_pct < self.LOW_BATTERY_WARNING:
            alert = await self._check_and_create_alert(
                frame,
                AlertType.LOW_BATTERY,
                AlertSeverity.WARNING,
                f"Low battery warning: {frame.battery_pct}% remaining"
            )
        
        # Rule 2: Low Battery Critical
        if frame.battery_pct < self.LOW_BATTERY_CRITICAL:
            alert = await self._check_and_create_alert(
                frame,
                AlertType.LOW_BATTERY,
                AlertSeverity.CRITICAL,
                f"Critical battery level: {frame.battery_pct}% - mission abort required"
            )
        
        # Rule 3: Signal Loss
        if frame.signal_strength < self.SIGNAL_LOSS_THRESHOLD:
            alert = await self._check_and_create_alert(
                frame,
                AlertType.SIGNAL_LOSS,
                AlertSeverity.WARNING,
                f"Signal strength critically low: {frame.signal_strength}%"
            )
        
        # Rule 4: GPS Deviation - calculate from previous position
        # (Simplified - would need timestamp comparison in production)
        
        # Rule 5: Mission Abort
        if frame.mission_status == MissionStatus.ABORTED:
            alert = await self._check_and_create_alert(
                frame,
                AlertType.MISSION_ABORT,
                AlertSeverity.CRITICAL,
                f"Mission aborted for drone"
            )
        
        return alert
    
    async def _check_and_create_alert(
        self,
        frame: TelemetryFrame,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str
    ) -> Optional[Alert]:
        """
        Check debounce and create alert if needed.
        
        Args:
            frame: Telemetry frame
            alert_type: Type of alert
            severity: Alert severity
            message: Alert message
            
        Returns:
            Created alert or None if debounced
        """
        # Check debounce
        if not self._should_fire_alert(frame.drone_id, alert_type):
            return None
        
        # Create alert
        alert = Alert(
            id=uuid4(),
            drone_id=frame.drone_id,
            type=alert_type,
            severity=severity,
            message=message,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Optionally enhance with OpenAI
        if settings.OPENAI_API_KEY and alert_type in [
            AlertType.LOW_BATTERY,
            AlertType.MISSION_ABORT
        ]:
            enhanced_message = await self._enhance_alert_with_ai(alert, frame)
            if enhanced_message:
                alert.message = enhanced_message
        
        # Record alert time for debouncing
        self._record_alert(frame.drone_id, alert_type)
        
        # Store in fleet service
        fleet_service.add_alert(alert)
        
        # Notify callback
        if self._on_alert_callback:
            try:
                await self._on_alert_callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
        
        return alert
    
    def _should_fire_alert(self, drone_id: UUID, alert_type: AlertType) -> bool:
        """
        Check if alert should fire based on debounce period.
        
        Args:
            drone_id: Drone identifier
            alert_type: Type of alert
            
        Returns:
            True if alert should fire
        """
        if drone_id not in self._last_alert:
            return True
        
        last_time = self._last_alert[drone_id].get(alert_type)
        if not last_time:
            return True
        
        # Check if debounce period has passed
        elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
        return elapsed >= settings.ANOMALY_DEBOUNCE_SECONDS
    
    def _record_alert(self, drone_id: UUID, alert_type: AlertType) -> None:
        """
        Record alert time for debouncing.
        
        Args:
            drone_id: Drone identifier
            alert_type: Type of alert
        """
        if drone_id not in self._last_alert:
            self._last_alert[drone_id] = {}
        
        self._last_alert[drone_id][alert_type] = datetime.now(timezone.utc)
    
    async def _enhance_alert_with_ai(
        self,
        alert: Alert,
        frame: TelemetryFrame
    ) -> Optional[str]:
        """
        Enhance alert message using OpenAI API.
        
        Args:
            alert: Alert to enhance
            frame: Related telemetry frame
            
        Returns:
            Enhanced message or None on error
        """
        if not settings.OPENAI_API_KEY:
            return None
        
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            
            prompt = f"""Generate a concise, plain-English alert message for a drone operator.
            
Drone: {frame.drone_id}
Current Battery: {frame.battery_pct}%
Current Altitude: {frame.altitude_m}m
Speed: {frame.speed_mps} m/s
Signal: {frame.signal_strength}%
Mission Status: {frame.mission_status.value}

Alert Type: {alert.type.value}
Severity: {alert.severity.value}

Provide a 1-2 sentence description of the situation and recommended action.
Be specific and actionable."""

            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a drone fleet monitoring assistant. Generate concise, actionable alert messages."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except ImportError:
            logger.warning("OpenAI client not installed")
        except Exception as e:
            logger.error(f"Error enhancing alert with AI: {e}")
        
        return None
    
    async def evaluate_movement(
        self,
        current: TelemetryFrame,
        previous: TelemetryFrame
    ) -> Optional[Alert]:
        """
        Evaluate GPS movement for deviation.
        
        Args:
            current: Current telemetry frame
            previous: Previous telemetry frame
            
        Returns:
            Alert if deviation detected
        """
        if current.drone_id != previous.drone_id:
            return None
        
        # Calculate time difference
        time_delta = (current.timestamp - previous.timestamp).total_seconds()
        if time_delta <= 0:
            return None
        
        # Calculate movement in degrees
        lat_diff = abs(current.lat - previous.lat)
        lng_diff = abs(current.lng - previous.lng)
        movement = max(lat_diff, lng_diff)
        
        # Calculate deviation per second
        deviation = movement / time_delta
        
        # Check threshold
        if deviation > self.GPS_DEVIATION_THRESHOLD:
            return await self._check_and_create_alert(
                current,
                AlertType.GPS_DEVIATION,
                AlertSeverity.WARNING,
                f"Unusual GPS movement detected: {deviation:.4f} deg/sec"
            )
        
        return None


# Global anomaly engine instance
engine = AnomalyEngine()


async def get_engine() -> AnomalyEngine:
    """Get the global anomaly engine instance."""
    return engine
