"""
WebSocket gateway for the Drone Fleet Telemetry API.

Provides WebSocket endpoints for real-time telemetry streaming
with support for per-drone filtering and heartbeat management.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Set, Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from backend.config import settings
from backend.fleet.models import (
    TelemetryFrame, WSMessage, WSMessageType, WSSubscribeMessage
)
from backend.auth.jwt_handler import decode_token
from backend.telemetry.publisher import publisher
from backend.fleet.service import fleet_service

logger = logging.getLogger(__name__)

# Router with /ws prefix
router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """Manages WebSocket connections and message routing."""
    
    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: Dict[WebSocket, Dict[str, Any]] = {}
    
    async def connect(
        self,
        websocket: WebSocket,
        token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Accept a new WebSocket connection. Requires valid JWT token."""
        if not token:
            await websocket.close(code=4001, reason="Authentication required")
            return None
        
        token_data = decode_token(token)
        if not token_data:
            await websocket.close(code=4001, reason="Invalid or expired token")
            return None
        
        await websocket.accept()
        logger.info(f"WebSocket accepted for user {token_data.username}")
        
        metadata = {
            "websocket": websocket,
            "token_data": token_data,
            "subscribed_drones": None,
            "last_heartbeat": datetime.now(timezone.utc),
            "connected_at": datetime.now(timezone.utc)
        }
        
        self.active_connections[websocket] = metadata
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")
        
        return metadata
    
    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            del self.active_connections[websocket]
            logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")
    
    async def send_personal(
        self,
        websocket: WebSocket,
        message: dict
    ) -> None:
        """Send message to a specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    async def broadcast(self, message: dict, filter_drones: Optional[Set[str]] = None) -> None:
        """Broadcast message to all connected clients."""
        logger.debug(f"Broadcasting to {len(self.active_connections)} clients")
        disconnected = []
        
        for websocket, metadata in self.active_connections.items():
            if filter_drones is not None:
                subscribed = metadata.get("subscribed_drones")
                if subscribed is not None:
                    if not filter_drones.intersection(subscribed):
                        continue
            
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Error broadcasting to client: {e}")
                disconnected.append(websocket)
        
        for ws in disconnected:
            self.disconnect(ws)
    
    async def broadcast_telemetry(self, frame: TelemetryFrame) -> None:
        """Broadcast telemetry frame to all connected clients."""
        message = {
            "type": WSMessageType.TELEMETRY.value,
            "data": frame.model_dump(mode='json'),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast(message)
    
    async def broadcast_alert(self, alert: dict) -> None:
        """Broadcast alert to all connected clients."""
        message = {
            "type": WSMessageType.ALERT.value,
            "data": alert,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.broadcast(message)
    
    async def send_heartbeat(self, websocket: WebSocket) -> None:
        """Send heartbeat ping to client."""
        message = {
            "type": WSMessageType.HEARTBEAT.value,
            "data": {"timestamp": datetime.now(timezone.utc).isoformat()},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.send_personal(websocket, message)
    
    def update_subscription(
        self,
        websocket: WebSocket,
        subscribe: Optional[list] = None,
        unsubscribe: Optional[list] = None
    ) -> None:
        """Update client's drone subscriptions."""
        metadata = self.active_connections.get(websocket)
        if not metadata:
            return
        
        subscribed = metadata.get("subscribed_drones")
        
        if subscribe:
            if subscribed is None:
                subscribed = set(subscribe)
            else:
                subscribed.update(subscribe)
        
        if unsubscribe and subscribed:
            subscribed.difference_update(unsubscribe)
        
        metadata["subscribed_drones"] = subscribed


# Global connection manager instance
connection_manager = ConnectionManager()


@router.websocket("/telemetry")
async def websocket_telemetry_all(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT token for authentication")
):
    """WebSocket endpoint for streaming all drone telemetry."""
    metadata = await connection_manager.connect(websocket, token)
    if not metadata:
        return
    
    heartbeat_task: Optional[asyncio.Task] = None
    
    try:
        # Send initial snapshot
        snapshot = await get_fleet_snapshot()
        logger.info(f"Sending snapshot with {len(snapshot.get('drones', []))} drones")
        snapshot_message = WSMessage(
            type=WSMessageType.SNAPSHOT,
            data=snapshot
        )
        msg_dict = snapshot_message.model_dump(mode='json')
        logger.info(f"Message dict: {str(msg_dict)[:100]}")
        await websocket.send_text(json.dumps(msg_dict))
        logger.info(f"Snapshot sent successfully")
        
        # Start heartbeat task
        heartbeat_task = asyncio.create_task(send_periodic_heartbeat(websocket))
        
        # Listen for messages
        while True:
            data = await websocket.receive_text()
            
            try:
                message_data = json.loads(data)
                
                if "subscribe" in message_data or "unsubscribe" in message_data:
                    subscribe = message_data.get("subscribe")
                    unsubscribe = message_data.get("unsubscribe")
                    
                    connection_manager.update_subscription(
                        websocket,
                        subscribe=subscribe,
                        unsubscribe=unsubscribe
                    )
                    
                    logger.debug(f"Updated subscription: subscribe={subscribe}, unsubscribe={unsubscribe}")
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {data}")
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        connection_manager.disconnect(websocket)


@router.websocket("/telemetry/{drone_id}")
async def websocket_telemetry_single(
    websocket: WebSocket,
    drone_id: str,
    token: Optional[str] = Query(None, description="JWT token for authentication")
):
    """WebSocket endpoint for streaming single drone telemetry."""
    metadata = await connection_manager.connect(websocket, token)
    if not metadata:
        return
    
    connection_manager.update_subscription(websocket, subscribe=[drone_id])
    
    heartbeat_task: Optional[asyncio.Task] = None
    
    try:
        try:
            drone_uuid = UUID(drone_id)
            telemetry = fleet_service.get_drone_telemetry(drone_uuid)
            drone = fleet_service.get_drone(drone_uuid)
            
            if telemetry:
                snapshot_message = WSMessage(
                    type=WSMessageType.TELEMETRY,
                    data=telemetry.model_dump(mode='json')
                )
                await connection_manager.send_personal(websocket, snapshot_message.model_dump(mode='json'))
        except ValueError:
            logger.warning(f"Invalid drone ID: {drone_id}")
        
        heartbeat_task = asyncio.create_task(send_periodic_heartbeat(websocket))
        
        while True:
            data = await websocket.receive_text()
            
            try:
                message_data = json.loads(data)
                
                if "subscribe" in message_data or "unsubscribe" in message_data:
                    subscribe = message_data.get("subscribe")
                    unsubscribe = message_data.get("unsubscribe")
                    
                    connection_manager.update_subscription(
                        websocket,
                        subscribe=subscribe,
                        unsubscribe=unsubscribe
                    )
                    
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()
        connection_manager.disconnect(websocket)


async def send_periodic_heartbeat(websocket: WebSocket) -> None:
    """Send periodic heartbeat to keep connection alive."""
    while True:
        try:
            await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL)
            await connection_manager.send_heartbeat(websocket)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")


async def get_fleet_snapshot() -> dict:
    """Get snapshot of all drones with their latest telemetry."""
    logger.info("Getting fleet snapshot...")
    drones = fleet_service.list_drones()
    logger.info(f"Found {len(drones)} drones in service")
    result_drones = []
    
    for drone in drones:
        telemetry = fleet_service.get_drone_telemetry(drone.id)
        result_drones.append({
            "drone": drone.model_dump(mode='json'),
            "telemetry": telemetry.model_dump(mode='json') if telemetry else None
        })
    
    return {
        "drones": result_drones,
        "alerts": fleet_service.get_alerts(limit=20)
    }


async def handle_telemetry(frame: TelemetryFrame) -> None:
    """Handle incoming telemetry frame and broadcast to clients."""
    await connection_manager.broadcast_telemetry(frame)


async def handle_alert_gateway(alert: dict) -> None:
    """Handle incoming alert and broadcast to clients."""
    await connection_manager.broadcast_alert(alert)