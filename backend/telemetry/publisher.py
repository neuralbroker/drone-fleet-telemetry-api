"""
Telemetry publisher for the Drone Fleet Telemetry API.

Publishes telemetry frames to Redis Pub/Sub channels for
real-time streaming to WebSocket clients and other consumers.
"""
import asyncio
import json
import logging
from typing import Dict, Set, Callable, Awaitable, Optional
from uuid import UUID

from backend.redis_client import redis_client
from backend.fleet.models import TelemetryFrame

logger = logging.getLogger(__name__)


class TelemetryPublisher:
    """
    Publishes telemetry data to Redis Pub/Sub channels.
    
    Manages channel subscriptions and publishes telemetry frames
    to both per-drone channels and a global broadcast channel.
    """
    
    # Channel names
    GLOBAL_CHANNEL = "telemetry:all"
    
    def __init__(self):
        """Initialize the telemetry publisher."""
        self._subscribers: Set[str] = set()
        self._telemetry_callback: Optional[Callable[[TelemetryFrame], Awaitable[None]]] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Queue for incoming telemetry
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    
    async def start(self) -> None:
        """Start the publisher."""
        if self._running:
            logger.warning("Telemetry publisher already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info("Telemetry publisher started")
    
    async def stop(self) -> None:
        """Stop the publisher."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Telemetry publisher stopped")
    
    async def publish(self, frame: TelemetryFrame) -> None:
        """
        Publish a telemetry frame to Redis channels.
        
        Args:
            frame: Telemetry frame to publish
        """
        # Add to processing queue
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            logger.warning("Telemetry queue full, dropping frame")
    
    async def _process_queue(self) -> None:
        """Process telemetry frames from queue and publish to Redis."""
        while self._running:
            try:
                # Get frame from queue with timeout
                frame = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0
                )
                
                # Serialize frame to JSON
                data = frame.model_dump_json()
                
                # Publish to global channel
                if redis_client.is_connected:
                    try:
                        await redis_client.publish(self.GLOBAL_CHANNEL, data)
                    except Exception as e:
                        logger.warning(f"Failed to publish to global channel: {e}")
                
                # Publish to drone-specific channel
                if redis_client.is_connected:
                    drone_channel = f"telemetry:{frame.drone_id}"
                    try:
                        await redis_client.publish(drone_channel, data)
                    except Exception as e:
                        logger.warning(f"Failed to publish to drone channel: {e}")
                
                # Also store latest telemetry in Redis hash for quick access
                if redis_client.is_connected:
                    await self._store_latest_telemetry(frame)
                
                # Call external callback if set
                if self._telemetry_callback:
                    try:
                        await self._telemetry_callback(frame)
                    except Exception as e:
                        logger.error(f"Error in telemetry callback: {e}")
                
            except asyncio.TimeoutError:
                # No items in queue, continue waiting
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error publishing telemetry: {e}")
                # Continue processing despite errors
    
    async def _store_latest_telemetry(self, frame: TelemetryFrame) -> None:
        """
        Store latest telemetry frame in Redis hash for quick access.
        
        Args:
            frame: Telemetry frame to store
        """
        try:
            key = f"telemetry:latest:{frame.drone_id}"
            data = frame.model_dump_json()
            await redis_client.set(key, data, expire=300)  # 5 min TTL
        except Exception as e:
            logger.error(f"Error storing latest telemetry: {e}")
    
    async def get_latest_telemetry(self, drone_id: UUID) -> Optional[TelemetryFrame]:
        """
        Get the latest telemetry frame for a drone.
        
        Args:
            drone_id: Drone identifier
            
        Returns:
            Latest telemetry frame or None
        """
        try:
            key = f"telemetry:latest:{drone_id}"
            data = await redis_client.get(key)
            if data:
                return TelemetryFrame.model_validate_json(data)
        except Exception as e:
            logger.error(f"Error getting latest telemetry: {e}")
        return None
    
    async def get_all_latest_telemetry(self) -> Dict[UUID, TelemetryFrame]:
        """
        Get latest telemetry for all drones.
        
        Returns:
            Dictionary mapping drone IDs to latest telemetry frames
        """
        result = {}
        
        try:
            # Find all latest telemetry keys
            keys = await redis_client.keys("telemetry:latest:*")
            
            for key in keys:
                # Extract drone ID from key
                drone_id_str = key.replace("telemetry:latest:", "")
                try:
                    drone_id = UUID(drone_id_str)
                    telemetry = await self.get_latest_telemetry(drone_id)
                    if telemetry:
                        result[drone_id] = telemetry
                except ValueError:
                    continue
                    
        except Exception as e:
            logger.error(f"Error getting all latest telemetry: {e}")
        
        return result
    
    def set_telemetry_callback(
        self,
        callback: Callable[[TelemetryFrame], Awaitable[None]]
    ) -> None:
        """
        Set callback for incoming telemetry frames.
        
        The callback is invoked after telemetry is published to Redis.
        
        Args:
            callback: Async function to call with telemetry frame
        """
        self._telemetry_callback = callback
    
    async def subscribe_to_drone(
        self,
        drone_id: UUID,
        callback: Callable[[TelemetryFrame], Awaitable[None]]
    ) -> None:
        """
        Subscribe to a specific drone's telemetry.
        
        Args:
            drone_id: Drone to subscribe to
            callback: Callback function for telemetry frames
        """
        channel = f"telemetry:{drone_id}"
        self._subscribers.add(channel)
        logger.debug(f"Subscribed to {channel}")
    
    async def unsubscribe_from_drone(self, drone_id: UUID) -> None:
        """
        Unsubscribe from a drone's telemetry.
        
        Args:
            drone_id: Drone to unsubscribe from
        """
        channel = f"telemetry:{drone_id}"
        self._subscribers.discard(channel)
        logger.debug(f"Unsubscribed from {channel}")


# Global publisher instance
publisher = TelemetryPublisher()


async def get_publisher() -> TelemetryPublisher:
    """Get the global telemetry publisher instance."""
    return publisher
