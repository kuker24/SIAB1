"""
Rate Limiter using Redis
Sliding window algorithm for precise rate limiting.
"""
import time
import logging
from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Redis-based rate limiter using sliding window algorithm.

    Usage:
        limiter = RateLimiter(key_prefix="submit_answer", limit=10, window=60)
        if await limiter.is_allowed(user_id):
            # Process request
        else:
            # Return 429 Too Many Requests
    """

    def __init__(self, key_prefix: str, limit: int, window: int):
        """
        Initialize rate limiter.

        Args:
            key_prefix: Prefix for Redis keys
            limit: Maximum requests allowed
            window: Time window in seconds
        """
        self.key_prefix = key_prefix
        self.limit = limit
        self.window = window

    def _get_key(self, identifier: str) -> str:
        """Generate Redis key for identifier."""
        return f"ratelimit:{self.key_prefix}:{identifier}"

    async def is_allowed(self, identifier: str) -> bool:
        """
        Check if request is allowed for identifier.

        Args:
            identifier: User ID, session ID, or IP address

        Returns:
            True if allowed, False if rate limited
        """
        try:
            redis = await get_redis()
            key = self._get_key(identifier)
            now = time.time()
            window_start = now - self.window

            pipe = redis.pipeline()

            # Remove old entries outside window
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current requests in window
            pipe.zcard(key)

            # Add current request with unique member to avoid same-timestamp collisions
            request_member = f"{now:.6f}:{time.time_ns()}"
            pipe.zadd(key, {request_member: now})

            # Set expiry on key
            pipe.expire(key, self.window + 1)

            results = await pipe.execute()
            current_count = results[1]

            return current_count < self.limit
        except Exception as e:
            logger.warning(f"Rate limiter Redis error (is_allowed): {e}. Failing open.")
            return True  # Fail-open: allow request when Redis is unavailable

    async def get_remaining(self, identifier: str) -> int:
        """Get remaining requests for identifier."""
        try:
            redis = await get_redis()
            key = self._get_key(identifier)
            now = time.time()
            window_start = now - self.window

            # Clean and count
            await redis.zremrangebyscore(key, 0, window_start)
            current_count = await redis.zcard(key)

            return max(0, self.limit - current_count)
        except Exception as e:
            logger.warning(f"Rate limiter Redis error (get_remaining): {e}. Returning full limit.")
            return self.limit  # Fail-open: report full limit available

    async def reset(self, identifier: str):
        """Reset rate limit for identifier."""
        redis = await get_redis()
        key = self._get_key(identifier)
        await redis.delete(key)


# Pre-configured rate limiters
class RateLimiters:
    """Pre-configured rate limiters for common use cases.

    IMPORTANT: All rate limiters use USER-BASED limiting (not IP-based).
    This is to handle CGNAT scenarios where hundreds of students share the same public IP.
    For login (before user is known), we use a very high limit.
    """

    # Answer submission: 60 per minute per session (1 per second is reasonable)
    # Uses session_id for identification (user-based)
    ANSWER_SUBMIT = RateLimiter(
        key_prefix="answer_submit",
        limit=60,
        window=60
    )

    # Exam submission: 10 per minute per user (prevent spam but allow retries)
    # Uses user_id for identification
    EXAM_SUBMIT = RateLimiter(
        key_prefix="exam_submit",
        limit=10,
        window=60
    )

    # Login attempts: 120 per minute per username+IP key
    # account_lockout.py remains the primary brute-force protection.
    LOGIN_ATTEMPT = RateLimiter(
        key_prefix="login_attempt",
        limit=120,
        window=60
    )

    # API general: 300 per minute per user (for high concurrency)
    # Uses user_id for identification (not IP)
    API_GENERAL = RateLimiter(
        key_prefix="api_general",
        limit=300,
        window=60
    )

    # SEB file generation: 10 per hour per user
    SEB_GENERATE = RateLimiter(
        key_prefix="seb_generate",
        limit=10,
        window=3600
    )

    # Exam Join (Token Guessing Protection): 10 per minute per user
    # Uses user_id for identification
    # Prevents brute-forcing 6-char token
    JOIN_EXAM = RateLimiter(
        key_prefix="join_exam",
        limit=10,
        window=60
    )


async def check_rate_limit(limiter: RateLimiter, identifier: str) -> tuple[bool, int]:
    """
    Check rate limit and return status.

    Returns:
        (is_allowed, remaining_requests)
    """
    try:
        is_allowed = await limiter.is_allowed(identifier)
        remaining = await limiter.get_remaining(identifier)
        return is_allowed, remaining
    except Exception as e:
        logger.warning(f"Rate limit check failed (Redis unavailable): {e}. Allowing request.")
        return True, limiter.limit  # Fail-open: allow request through
