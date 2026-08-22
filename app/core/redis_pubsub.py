"""
Redis Pub/Sub for WebSocket broadcasting across multiple replicas.
"""
import json
import asyncio
import os
from typing import Dict, Optional, Any, Callable
from redis import asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
from app.config import settings

redis_client: Optional[aioredis.Redis] = None
redis_client_lock = asyncio.Lock()


async def init_redis():
    """Initialize Redis connection."""
    global redis_client
    if redis_client is not None:
        return redis_client

    async with redis_client_lock:
        if redis_client is not None:
            return redis_client

        socket_connect_timeout = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "3.0"))
        socket_timeout = float(os.getenv("REDIS_SOCKET_TIMEOUT", "3.0"))
        max_connections = max(100, int(os.getenv("REDIS_MAX_CONNECTIONS", "1000")))

        redis_client = await aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            encoding="utf-8",
            health_check_interval=30,
            socket_keepalive=True,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
            max_connections=max_connections,
            retry_on_timeout=True,
            retry_on_error=[ConnectionError, TimeoutError, OSError],
        )
        return redis_client


async def close_redis():
    """Close Redis connection."""
    global redis_client
    async with redis_client_lock:
        if redis_client:
            try:
                await redis_client.close()
            except (RedisConnectionError, RedisTimeoutError):
                pass
            redis_client = None


async def get_redis() -> aioredis.Redis:
    """Get Redis client instance."""
    if redis_client is None:
        await init_redis()
    return redis_client


async def publish_message(channel: str, message: Dict[str, Any]):
    """Publish message to Redis channel."""
    redis = await get_redis()
    await redis.publish(channel, json.dumps(message))


async def subscribe_channel(channel: str, callback: Callable):
    """Subscribe to Redis channel and call callback on message."""
    import logging
    logger = logging.getLogger(__name__)

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message['type'] == 'message':
                data = json.loads(message['data'])
                await callback(data)
    except asyncio.CancelledError:
        logger.debug(f"Subscription to {channel} cancelled")
    except Exception as e:
        logger.error(f"Error in Redis subscription for {channel}: {e}", exc_info=True)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


# Cache utilities
async def cache_set(key: str, value: Any, expire: int = 3600):
    """Set a cached value with expiration."""
    redis = await get_redis()
    await redis.set(key, json.dumps(value), ex=expire)


async def cache_get(key: str) -> Optional[Any]:
    """Get a cached value."""
    redis = await get_redis()
    value = await redis.get(key)
    if value:
        return json.loads(value)
    return None


async def cache_delete(key: str):
    """Delete a cached value."""
    redis = await get_redis()
    await redis.delete(key)


# Session utilities
async def store_session_data(session_id: int, data: Dict[str, Any]):
    """Store exam session data in Redis."""
    key = f"exam_session:{session_id}"
    await cache_set(key, data, expire=7200)  # 2 hours


async def get_session_data(session_id: int) -> Optional[Dict[str, Any]]:
    """Get exam session data from Redis."""
    key = f"exam_session:{session_id}"
    return await cache_get(key)


async def update_session_answers(session_id: int, answers: Dict[Any, Any]):
    """Update cached answers for a session."""
    key = f"exam_answers:{session_id}"
    await cache_set(key, answers, expire=7200)


async def update_session_activity(exam_id: int, user_id: int, activity_data: Dict[str, Any]):
    """Update session activity/heartbeat."""
    key = f"exam_activity:{exam_id}:{user_id}"
    await cache_set(key, activity_data, expire=300)


async def get_session_activity(exam_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Get session activity/heartbeat."""
    key = f"exam_activity:{exam_id}:{user_id}"
    return await cache_get(key)


async def get_session_answers(session_id: int) -> Optional[Dict[int, int]]:
    """Get cached answers for a session."""
    key = f"exam_answers:{session_id}"
    return await cache_get(key)
