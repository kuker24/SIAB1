"""
Cache Manager - Enterprise-grade caching layer
Provides decorator-based caching, cache warming, and invalidation strategies.
"""
from functools import wraps
from typing import Optional, Callable
import json
import hashlib
import asyncio
import logging

from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Centralized cache management with decorator support.

    Usage:
        @cache_manager.cached(ttl=300, key_prefix="exam")
        async def get_exam(exam_id: int):
            return await db.query(...)
    """

    def __init__(self):
        self.default_ttl = 300  # 5 minutes

    async def get(self, key: str) -> Optional[str]:
        """Get raw value from cache."""
        try:
            redis = await get_redis()
            return await redis.get(key)
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None

    async def set(self, key: str, value: str, ttl: int = None) -> bool:
        """Set raw value in cache."""
        try:
            redis = await get_redis()
            return await redis.setex(key, ttl or self.default_ttl, value)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    def _generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate unique cache key from function arguments."""
        # Create deterministic key from arguments
        key_parts = [prefix]

        # Add positional args
        for arg in args:
            if isinstance(arg, (str, int, float, bool)):
                key_parts.append(str(arg))
            else:
                # For complex objects, use hash
                key_parts.append(hashlib.md5(str(arg).encode()).hexdigest()[:8])

        # Add keyword args (sorted for consistency)
        for k, v in sorted(kwargs.items()):
            if isinstance(v, (str, int, float, bool)):
                key_parts.append(f"{k}={v}")

        return ":".join(key_parts)

    def cached(
        self,
        ttl: int = None,
        key_prefix: str = "cache",
        skip_cache: Callable = None
    ):
        """
        Decorator for caching async function results.

        Args:
            ttl: Time-to-live in seconds (default: 300)
            key_prefix: Prefix for cache key
            skip_cache: Optional callable to determine if cache should be skipped

        Example:
            @cache_manager.cached(ttl=600, key_prefix="exam")
            async def get_exam(exam_id: int):
                return await db.execute(...)
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Check if caching should be skipped
                if skip_cache and skip_cache(*args, **kwargs):
                    return await func(*args, **kwargs)

                # Generate cache key
                cache_key = self._generate_cache_key(key_prefix, *args, **kwargs)

                try:
                    redis = await get_redis()

                    # Try to get from cache
                    cached_value = await redis.get(cache_key)

                    if cached_value:
                        logger.debug(f"Cache HIT: {cache_key}")
                        return json.loads(cached_value)

                    # Cache miss - execute function
                    logger.debug(f"Cache MISS: {cache_key}")
                    result = await func(*args, **kwargs)

                    # Store in cache
                    cache_ttl = ttl or self.default_ttl
                    await redis.setex(
                        cache_key,
                        cache_ttl,
                        json.dumps(result, default=str)
                    )

                    return result

                except Exception as e:
                    logger.error(f"Cache error for {cache_key}: {e}")
                    # On cache failure, execute function normally
                    return await func(*args, **kwargs)

            # Add cache invalidation method to function
            async def invalidate(*args, **kwargs):
                """Invalidate cache for this function call."""
                cache_key = self._generate_cache_key(key_prefix, *args, **kwargs)
                try:
                    redis = await get_redis()
                    await redis.delete(cache_key)
                    logger.info(f"Cache invalidated: {cache_key}")
                except Exception as e:
                    logger.error(f"Cache invalidation error: {e}")

            wrapper.invalidate = invalidate
            return wrapper

        return decorator

    async def invalidate_pattern(self, pattern: str):
        """
        Invalidate all cache keys matching a pattern.

        Example:
            await cache_manager.invalidate_pattern("exam:*")
        """
        try:
            redis = await get_redis()
            cursor = 0
            deleted_count = 0

            while True:
                cursor, keys = await redis.scan(cursor, match=pattern, count=100)

                if keys:
                    await redis.delete(*keys)
                    deleted_count += len(keys)

                if cursor == 0:
                    break

            logger.info(f"Invalidated {deleted_count} keys matching pattern: {pattern}")
            return deleted_count

        except Exception as e:
            logger.error(f"Pattern invalidation error: {e}")
            return 0

    async def warm_cache(self, func: Callable, args_list: list):
        """
        Warm cache by pre-loading data for common queries.

        Example:
            await cache_manager.warm_cache(
                get_exam,
                [(1,), (2,), (3,)]  # List of argument tuples
            )
        """
        logger.info(f"Warming cache for {func.__name__} with {len(args_list)} entries")

        tasks = []
        for args in args_list:
            if isinstance(args, tuple):
                tasks.append(func(*args))
            else:
                tasks.append(func(args))

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"Cache warmed successfully for {func.__name__}")
        except Exception as e:
            logger.error(f"Cache warming error: {e}")

    async def get_cache_stats(self) -> dict:
        """Get cache statistics from Redis."""
        try:
            redis = await get_redis()
            info = await redis.info()

            return {
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                ),
                "used_memory": info.get("used_memory_human", "0M"),
                "connected_clients": info.get("connected_clients", 0)
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}

    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage."""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)


# Singleton instance
cache_manager = CacheManager()


# Convenience decorators with pre-configured TTLs
def cache_short(key_prefix: str = "cache"):
    """Cache for 5 minutes (short-lived data)."""
    return cache_manager.cached(ttl=300, key_prefix=key_prefix)


def cache_medium(key_prefix: str = "cache"):
    """Cache for 15 minutes (medium-lived data)."""
    return cache_manager.cached(ttl=900, key_prefix=key_prefix)


def cache_long(key_prefix: str = "cache"):
    """Cache for 1 hour (long-lived data)."""
    return cache_manager.cached(ttl=3600, key_prefix=key_prefix)


# Specific cache strategies for common patterns
def cache_exam_metadata(ttl: int = 900):
    """Cache exam metadata (15 min default, invalidate on exam update)."""
    return cache_manager.cached(ttl=ttl, key_prefix="exam_meta")


def cache_user_profile(ttl: int = 1800):
    """Cache user profile data (30 min default)."""
    return cache_manager.cached(ttl=ttl, key_prefix="user_profile")


def cache_question_bank(ttl: int = 3600):
    """Cache question bank queries (1 hour default)."""
    return cache_manager.cached(ttl=ttl, key_prefix="question_bank")


def cache_system_settings(ttl: int = 300):
    """Cache system settings (5 min default)."""
    return cache_manager.cached(ttl=ttl, key_prefix="system_settings")
