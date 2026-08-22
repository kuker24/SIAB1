"""
Performance Optimization Middleware
Adds compression, caching, and monitoring for SSS+++++ performance
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging
from typing import Callable
import hashlib

logger = logging.getLogger(__name__)

class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Ultra-optimized performance middleware
    - Request timing
    - Response caching
    - Performance monitoring
    """

    # Simple in-memory cache (use Redis in production)
    _cache = {}
    _cache_ttl = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start timer
        start_time = time.time()

        # Check cache for GET requests
        if request.method == "GET":
            cache_key = self._get_cache_key(request)
            cached = self._get_from_cache(cache_key)
            if cached:
                response = Response(
                    content=cached["body"],
                    status_code=200,
                    headers=cached["headers"],
                    media_type=cached.get("media_type", "application/json")
                )
                response.headers["X-Cache"] = "HIT"
                return response

        # Process request
        response = await call_next(request)

        # Calculate processing time
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)

        # Cache successful GET responses
        if request.method == "GET" and response.status_code == 200:
            cache_key = self._get_cache_key(request)
            await self._save_to_cache(cache_key, response, ttl=300)  # 5 minutes

        # Add performance headers
        response.headers["X-Server-Timing"] = f"total;dur={process_time*1000}"

        return response

    def _get_cache_key(self, request: Request) -> str:
        """Generate cache key from request"""
        url = str(request.url)
        # Include auth token in cache key for user-specific data
        auth_header = request.headers.get("authorization", "")
        key = f"{url}:{auth_header}"
        return hashlib.md5(key.encode()).hexdigest()

    def _get_from_cache(self, key: str):
        """Get from cache if not expired"""
        if key not in self._cache:
            return None

        if key in self._cache_ttl:
            if time.time() > self._cache_ttl[key]:
                # Expired
                del self._cache[key]
                del self._cache_ttl[key]
                return None

        return self._cache[key]

    async def _save_to_cache(self, key: str, response: Response, ttl: int = 300):
        """Save to cache with TTL"""
        # Read response body
        body = b"".join([chunk async for chunk in response.body_iterator])

        # Store in cache
        self._cache[key] = {
            "body": body,
            "headers": dict(response.headers),
            "media_type": response.media_type
        }
        self._cache_ttl[key] = time.time() + ttl

        # Reconstruct response body iterator
        async def generate():
            yield body

        response.body_iterator = generate()


def add_performance_middleware(app: FastAPI):
    """
    Add all performance optimizations to FastAPI app
    """

    # 1. GZip compression (50-70% size reduction)
    app.add_middleware(
        GZipMiddleware,
        minimum_size=1000,  # Only compress responses > 1KB
        compresslevel=6  # Balance between speed and compression
    )

    # 2. Performance monitoring and caching
    app.add_middleware(PerformanceMiddleware)

    # 3. CORS with caching
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure based on your needs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=3600  # Cache preflight requests for 1 hour
    )

    logger.info("Performance middleware enabled:")
    logger.info("  - GZip compression (50-70% reduction)")
    logger.info("  - Response caching (5 min TTL)")
    logger.info("  - Performance timing headers")
    logger.info("  - CORS with caching")
