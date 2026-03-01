"""
Configuration module for the Drone Fleet Telemetry API.

Uses Pydantic BaseSettings for environment variable management with validation.
All configuration is loaded from environment variables with sensible defaults.
"""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    Application configuration settings.
    
    All settings are loaded from environment variables with fallback defaults.
    For production, set these environment variables before deployment.
    """
    
    # Application
    APP_NAME: str = Field(default="Drone Fleet Telemetry API", description="Application name")
    APP_VERSION: str = Field(default="1.0.0", description="API version")
    DEBUG: bool = Field(default=False, description="Debug mode flag")
    
    # Server
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8000, description="Server port")
    
    # Redis
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    REDIS_MAX_CONNECTIONS: int = Field(
        default=50,
        description="Maximum Redis connection pool size"
    )
    REDIS_HEALTH_CHECK_INTERVAL: int = Field(
        default=30,
        description="Redis health check interval in seconds"
    )
    
    # JWT Authentication
    JWT_SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="JWT secret key for token signing"
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=1440,  # 24 hours
        description="JWT token expiration in minutes"
    )
    
    # Telemetry Simulation
    SIMULATOR_ENABLED: bool = Field(
        default=True,
        description="Enable/disable telemetry simulation"
    )
    SIMULATOR_DRONES_COUNT: int = Field(
        default=5,
        description="Number of simulated drones"
    )
    SIMULATOR_TELEMETRY_INTERVAL: float = Field(
        default=1.0,
        description="Telemetry publish interval in seconds"
    )
    
    # Anomaly Detection
    ANOMALY_DEBOUNCE_SECONDS: int = Field(
        default=30,
        description="Alert debounce period in seconds"
    )
    MAX_ALERTS_PER_DRONE: int = Field(
        default=100,
        description="Maximum alerts to store per drone"
    )
    
    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = Field(
        default=30,
        description="WebSocket heartbeat ping interval in seconds"
    )
    WS_MESSAGE_QUEUE_SIZE: int = Field(
        default=1000,
        description="WebSocket message queue size per connection"
    )
    
    # OpenAI (Optional)
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenAI API key for alert summarization"
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model to use for alerts"
    )
    
    # CORS
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins"
    )
    
    # Database (for future use - using in-memory/Redis for now)
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="PostgreSQL database URL (optional)"
    )
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Allow extra env vars without error


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """
    Get the global settings instance.
    
    Returns:
        Settings: The application settings singleton
    """
    return settings
