"""
Main application entry point for the Drone Fleet Telemetry API.

Configures FastAPI application with all routes, middleware,
and background tasks for telemetry simulation and streaming.
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.redis_client import redis_client
from backend.fleet.service import fleet_service
from backend.fleet.routes import router as fleet_router, missions_router, alerts_router
from backend.auth.routes import router as auth_router
from backend.telemetry.simulator import simulator
from backend.telemetry.publisher import publisher
from backend.telemetry.websocket_gateway import router as ws_router
from backend.anomaly.engine import engine

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.
    
    Manages startup and shutdown of background tasks and connections.
    """
    # Startup
    logger.info("Starting Drone Fleet Telemetry API...")
    
    # Connect to Redis
    try:
        await redis_client.connect()
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        # Continue without Redis for development
    
    # Initialize fleet service
    await fleet_service.initialize()
    
    # Start telemetry simulator
    if settings.SIMULATOR_ENABLED:
        await simulator.start()
        logger.info("Telemetry simulator started")
        
        # Re-initialize fleet service after simulator starts to get drones
        await fleet_service.initialize()
        
        # Set up simulator callbacks
        async def on_telemetry(frame):
            # Publish to Redis
            await publisher.publish(frame)
            
            # Update fleet service cache
            fleet_service.update_telemetry(frame)
            
            # Send to WebSocket clients
            from backend.telemetry.websocket_gateway import handle_telemetry
            await handle_telemetry(frame)
            
            # Evaluate for anomalies
            await engine.evaluate(frame)
        
        simulator.on_telemetry = on_telemetry
    
    # Start telemetry publisher
    await publisher.start()
    
    # Start anomaly engine
    await engine.start()
    
    # Set up anomaly callback to send alerts via WebSocket
    async def on_alert(alert):
        from backend.telemetry.websocket_gateway import handle_alert_gateway
        await handle_alert_gateway(alert.model_dump())
    
    engine.set_alert_callback(on_alert)
    
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Drone Fleet Telemetry API...")
    
    # Stop components
    await simulator.stop()
    await publisher.stop()
    await engine.stop()
    await redis_client.disconnect()
    
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Real-time drone fleet telemetry API with WebSocket streaming",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return {
        "status": "healthy",
        "redis_connected": redis_client.is_connected,
        "simulator_running": simulator.is_running
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc"
    }


# Include routers
app.include_router(auth_router)
app.include_router(fleet_router)
app.include_router(missions_router)
app.include_router(alerts_router)
app.include_router(ws_router, prefix="/ws")


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
