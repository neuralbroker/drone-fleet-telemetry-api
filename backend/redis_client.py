"""
Async Redis client singleton for the Drone Fleet Telemetry API.

Provides a connection pool and pub/sub capabilities for real-time
telemetry streaming and state management.
"""
import asyncio
import logging
from typing import Optional, Any
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from backend.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Async Redis client singleton with connection pooling.
    
    Manages a connection pool for efficient Redis operations and
    provides pub/sub capabilities for telemetry streaming.
    """
    
    _instance: Optional["RedisClient"] = None
    _redis: Optional[Redis] = None
    _connection_lock: asyncio.Lock = asyncio.Lock()
    _health_check_task: Optional[asyncio.Task] = None
    _is_healthy: bool = False
    
    def __new__(cls) -> "RedisClient":
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def is_connected(self) -> bool:
        """Check if Redis connection is active."""
        return self._redis is not None and self._is_healthy
    
    async def connect(self, max_retries: int = 5, retry_delay: float = 2.0) -> None:
        """
        Initialize Redis connection with connection pooling and retry logic.
        
        Creates a connection pool with configurable max connections
        and tests the connection immediately. Implements exponential backoff
        for connection retries.
        
        Args:
            max_retries: Maximum number of connection attempts
            retry_delay: Initial delay between retries (doubles each attempt)
        """
        async with self._connection_lock:
            if self._redis is not None:
                logger.info("Redis client already initialized")
                return
            
            attempt = 0
            current_delay = retry_delay
            
            while attempt < max_retries:
                attempt += 1
                try:
                    logger.info(f"Connecting to Redis at {settings.REDIS_URL} (attempt {attempt}/{max_retries})")
                    
                    # Create connection pool
                    pool = redis.ConnectionPool.from_url(
                        settings.REDIS_URL,
                        max_connections=settings.REDIS_MAX_CONNECTIONS,
                        decode_responses=True,
                        socket_keepalive=True,
                        socket_connect_timeout=5,
                    )
                    
                    # Create Redis client from pool
                    self._redis = redis.Redis(connection_pool=pool)
                    
                    # Test connection
                    await self._redis.ping()
                    self._is_healthy = True
                    
                    logger.info("Redis connection established successfully")
                    
                    # Start background health check
                    self._start_health_check()
                    return
                    
                except (RedisConnectionError, Exception) as e:
                    logger.warning(f"Redis connection attempt {attempt} failed: {e}")
                    self._redis = None
                    self._is_healthy = False
                    
                    if attempt < max_retries:
                        logger.info(f"Retrying in {current_delay} seconds...")
                        await asyncio.sleep(current_delay)
                        current_delay = min(current_delay * 2, 30)  # Exponential backoff, max 30s
            
            # All retries exhausted - just log and continue
            logger.warning(f"Could not connect to Redis after {max_retries} attempts - continuing without Redis")
    
    async def disconnect(self) -> None:
        """
        Gracefully disconnect from Redis.
        
        Cancels health check task and closes connection pool.
        """
        async with self._connection_lock:
            # Cancel health check
            if self._health_check_task and not self._health_check_task.done():
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            # Close connection
            if self._redis:
                await self._redis.aclose()
                self._redis = None
                self._is_healthy = False
                logger.info("Redis connection closed")
    
    def _start_health_check(self) -> None:
        """Start background health check task."""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(
                self._health_check_loop()
            )
            logger.debug("Redis health check task started")
    
    async def _health_check_loop(self) -> None:
        """
        Periodic health check to verify Redis connectivity.
        
        Runs every settings.REDIS_HEALTH_CHECK_INTERVAL seconds.
        """
        while True:
            try:
                await asyncio.sleep(settings.REDIS_HEALTH_CHECK_INTERVAL)
                
                if self._redis:
                    await self._redis.ping()
                    if not self._is_healthy:
                        self._is_healthy = True
                        logger.info("Redis connection restored")
            except asyncio.CancelledError:
                break
            except RedisError as e:
                if self._is_healthy:
                    self._is_healthy = False
                    logger.warning(f"Redis health check failed: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in health check: {e}")
    
    async def get(self, key: str) -> Optional[str]:
        """
        Get value by key.
        
        Args:
            key: Redis key
            
        Returns:
            Value as string, or None if key doesn't exist
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.get(key)
    
    async def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ) -> bool:
        """
        Set key-value pair with optional expiration.
        
        Args:
            key: Redis key
            value: Value to store
            expire: Expiration time in seconds (optional)
            
        Returns:
            True if set successfully
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        
        if expire:
            return await self._redis.set(key, value, ex=expire)
        return await self._redis.set(key, value)
    
    async def delete(self, key: str) -> int:
        """
        Delete key(s) from Redis.
        
        Args:
            key: Redis key or pattern
            
        Returns:
            Number of keys deleted
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.delete(key)
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists.
        
        Args:
            key: Redis key
            
        Returns:
            True if key exists
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.exists(key) > 0
    
    async def publish(self, channel: str, message: Any) -> int:
        """
        Publish message to channel.
        
        Args:
            channel: Channel name
            message: Message to publish
            
        Returns:
            Number of subscribers that received the message
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.publish(channel, message)
    
    @asynccontextmanager
    async def pubsub(self):
        """
        Create a pub/sub context manager.
        
        Yields:
            Redis pub/sub client
            
        Usage:
            async with redis_client.pubsub() as pub:
                await pub.subscribe("channel")
                async for message in pub.listen():
                    ...
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        
        pubsub = self._redis.pubsub()
        try:
            yield pubsub
        finally:
            await pubsub.close()
    
    async def lpush(self, key: str, *values: Any) -> int:
        """
        Push values to left of list.
        
        Args:
            key: List key
            values: Values to push
            
        Returns:
            Length of list after push
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.lpush(key, *values)
    
    async def lrange(self, key: str, start: int, end: int) -> list:
        """
        Get range of list elements.
        
        Args:
            key: List key
            start: Start index
            end: End index (-1 for all)
            
        Returns:
            List of values
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.lrange(key, start, end)
    
    async def ltrim(self, key: str, start: int, end: int) -> bool:
        """
        Trim list to specified range.
        
        Args:
            key: List key
            start: Start index
            end: End index (-1 for all)
            
        Returns:
            True if trimmed successfully
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.ltrim(key, start, end)
    
    async def llen(self, key: str) -> int:
        """
        Get length of list.
        
        Args:
            key: List key
            
        Returns:
            Length of list
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.llen(key)
    
    async def hset(self, key: str, mapping: dict) -> int:
        """
        Set hash field(s).
        
        Args:
            key: Hash key
            mapping: Field-value mapping
            
        Returns:
            Number of fields set
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.hset(key, mapping=mapping)
    
    async def hgetall(self, key: str) -> dict:
        """
        Get all hash fields and values.
        
        Args:
            key: Hash key
            
        Returns:
            Dictionary of field-value pairs
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.hgetall(key)
    
    async def hget(self, key: str, field: str) -> Optional[str]:
        """
        Get hash field value.
        
        Args:
            key: Hash key
            field: Field name
            
        Returns:
            Field value or None
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.hget(key, field)
    
    async def keys(self, pattern: str) -> list:
        """
        Find keys matching pattern.
        
        Args:
            pattern: Key pattern (e.g., "telemetry:*")
            
        Returns:
            List of matching keys
        """
        if not self._redis:
            raise RuntimeError("Redis not connected")
        return await self._redis.keys(pattern)


# Global Redis client instance
redis_client = RedisClient()


async def get_redis() -> RedisClient:
    """
    Get the global Redis client instance.
    
    Returns:
        RedisClient: The singleton Redis client
    """
    return redis_client
