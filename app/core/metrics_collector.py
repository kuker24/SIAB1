"""
Metrics Collector Service
Collects system, database, and application metrics for monitoring dashboard.
"""
import psutil
import json
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy import text
from app.core.redis_pubsub import get_redis
import logging

logger = logging.getLogger(__name__)


REDIS_COUNTER_SNAPSHOT_KEY = "metrics:redis:counter_snapshot"
REDIS_COUNTER_SNAPSHOT_TTL_SECONDS = 172800


class MetricsCollector:
    """Collects and stores system metrics in Redis with TTL."""

    def __init__(self):
        self.redis = None
        self.metrics_ttl = 86400  # 24 hours
        self.collection_interval = 10  # seconds
        self.min_refresh_seconds = 5
        self._last_collected_at: Optional[datetime] = None
        self._last_payload: Optional[Dict[str, Any]] = None

    async def initialize(self):
        """Initialize Redis connection."""
        self.redis = await get_redis()

    async def collect_system_metrics(self) -> Dict[str, Any]:
        """Collect system-level metrics (CPU, Memory, Disk, Network)."""
        try:
            # Non-blocking sampling to keep monitoring endpoints responsive.
            cpu_percent = psutil.cpu_percent(interval=0.0)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            network = psutil.net_io_counters()

            metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "cpu": {
                    "percent": cpu_percent,
                    "count": psutil.cpu_count(),
                    "per_cpu": psutil.cpu_percent(percpu=True)
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent
                },
                "network": {
                    "bytes_sent": network.bytes_sent,
                    "bytes_recv": network.bytes_recv,
                    "packets_sent": network.packets_sent,
                    "packets_recv": network.packets_recv
                }
            }

            # Store in Redis
            if self.redis:
                await self.redis.setex(
                    "metrics:system:latest",
                    self.metrics_ttl,
                    json.dumps(metrics)
                )

            return metrics

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return {}

    async def collect_database_metrics(self, db) -> Dict[str, Any]:
        """Collect PostgreSQL performance metrics."""
        try:
            # Active connections
            result = await db.execute(text("""
                SELECT count(*) as active_connections
                FROM pg_stat_activity
                WHERE state = 'active'
            """))
            active_connections = result.scalar()

            # Total connections
            result = await db.execute(text("""
                SELECT count(*) as total_connections
                FROM pg_stat_activity
            """))
            total_connections = result.scalar()

            # Max connections
            result = await db.execute(text("SHOW max_connections"))
            max_connections = int(result.scalar())

            # Database size
            result = await db.execute(text("""
                SELECT pg_database_size(current_database()) as db_size
            """))
            db_size = result.scalar()

            # Cache hit ratio
            result = await db.execute(text("""
                SELECT
                    sum(heap_blks_hit) / NULLIF(sum(heap_blks_hit + heap_blks_read), 0) * 100 as cache_hit_ratio
                FROM pg_statio_user_tables
            """))
            cache_hit_ratio = result.scalar() or 0

            # Slow queries (queries running > 5 seconds)
            result = await db.execute(text("""
                SELECT count(*) as slow_queries
                FROM pg_stat_activity
                WHERE state = 'active'
                AND query_start < NOW() - INTERVAL '5 seconds'
                AND query NOT LIKE '%pg_stat_activity%'
            """))
            slow_queries = result.scalar()

            metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "connections": {
                    "active": active_connections,
                    "total": total_connections,
                    "max": max_connections,
                    "percent_used": (total_connections / max_connections * 100) if max_connections > 0 else 0
                },
                "database": {
                    "size_bytes": db_size,
                    "cache_hit_ratio": float(cache_hit_ratio)
                },
                "performance": {
                    "slow_queries": slow_queries
                }
            }

            # Store in Redis
            if self.redis:
                await self.redis.setex(
                    "metrics:database:latest",
                    self.metrics_ttl,
                    json.dumps(metrics)
                )

            return metrics

        except Exception as e:
            logger.error(f"Error collecting database metrics: {e}")
            return {}

    async def _compute_redis_window_stats(self, hits: int, misses: int) -> Dict[str, Any]:
        """
        Compute rolling cache-hit stats from counter deltas.

        Redis INFO counters are cumulative since process start; using deltas
        avoids false alarms caused by historical misses from older incidents.
        """
        window_payload: Dict[str, Any] = {
            "window_seconds": 0.0,
            "keyspace_hits_delta": 0,
            "keyspace_misses_delta": 0,
            "cache_lookup_delta": 0,
            "cache_hit_ratio_window": 100.0,
            "cache_ratio_source": "delta",
        }

        if not self.redis:
            return window_payload

        now_ts = datetime.utcnow().timestamp()
        try:
            previous_raw = await self.redis.get(REDIS_COUNTER_SNAPSHOT_KEY)
            if isinstance(previous_raw, bytes):
                previous_raw = previous_raw.decode("utf-8", errors="ignore")

            previous = json.loads(previous_raw) if previous_raw else {}
            prev_hits = int(previous.get("hits", 0))
            prev_misses = int(previous.get("misses", 0))
            prev_ts = float(previous.get("ts", 0.0))
            elapsed_seconds = max(1.0, now_ts - prev_ts) if prev_ts > 0 else 0.0

            if hits >= prev_hits and misses >= prev_misses and prev_ts > 0:
                hits_delta = hits - prev_hits
                misses_delta = misses - prev_misses
                lookup_delta = max(0, hits_delta + misses_delta)
                window_ratio = (hits_delta / lookup_delta * 100.0) if lookup_delta > 0 else 100.0
                window_payload.update(
                    {
                        "window_seconds": round(elapsed_seconds, 2),
                        "keyspace_hits_delta": int(hits_delta),
                        "keyspace_misses_delta": int(misses_delta),
                        "cache_lookup_delta": int(lookup_delta),
                        "cache_hit_ratio_window": float(window_ratio),
                    }
                )

            await self.redis.setex(
                REDIS_COUNTER_SNAPSHOT_KEY,
                REDIS_COUNTER_SNAPSHOT_TTL_SECONDS,
                json.dumps({"hits": int(hits), "misses": int(misses), "ts": now_ts}),
            )
        except Exception as exc:
            logger.debug("Redis window stats computation skipped: %s", exc)

        return window_payload

    async def collect_redis_metrics(self) -> Dict[str, Any]:
        """Collect Redis cache statistics."""
        try:
            if not self.redis:
                return {}

            info = await self.redis.info()
            maxmemory = int(info.get("maxmemory", 0) or 0)
            used_memory = int(info.get("used_memory", 0) or 0)
            memory_percent = (used_memory / maxmemory * 100.0) if maxmemory > 0 else 0.0
            keyspace_hits = int(info.get("keyspace_hits", 0) or 0)
            keyspace_misses = int(info.get("keyspace_misses", 0) or 0)
            total_error_replies = int(info.get("total_error_replies", 0) or 0)
            instantaneous_ops_per_sec = int(info.get("instantaneous_ops_per_sec", 0) or 0)

            metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "memory": {
                    "used_memory": used_memory,
                    "used_memory_peak": int(info.get("used_memory_peak", 0) or 0),
                    "used_memory_rss": int(info.get("used_memory_rss", 0) or 0),
                    "maxmemory": maxmemory,
                    "percent_used_of_maxmemory": round(memory_percent, 3),
                },
                "stats": {
                    "total_connections_received": int(info.get("total_connections_received", 0) or 0),
                    "total_commands_processed": int(info.get("total_commands_processed", 0) or 0),
                    "keyspace_hits": keyspace_hits,
                    "keyspace_misses": keyspace_misses,
                    "evicted_keys": int(info.get("evicted_keys", 0) or 0),
                    "instantaneous_ops_per_sec": instantaneous_ops_per_sec,
                    "total_error_replies": total_error_replies,
                },
                "clients": {
                    "connected_clients": int(info.get("connected_clients", 0) or 0),
                    "blocked_clients": int(info.get("blocked_clients", 0) or 0)
                }
            }

            # Calculate cache hit ratio
            hits = metrics["stats"]["keyspace_hits"]
            misses = metrics["stats"]["keyspace_misses"]
            total = hits + misses
            metrics["stats"]["cache_hit_ratio"] = (hits / total * 100) if total > 0 else 0
            metrics["stats"].update(
                await self._compute_redis_window_stats(hits=hits, misses=misses)
            )

            # Store in Redis
            await self.redis.setex(
                "metrics:redis:latest",
                self.metrics_ttl,
                json.dumps(metrics)
            )

            return metrics

        except Exception as e:
            logger.error(f"Error collecting Redis metrics: {e}")
            return {}

    async def collect_application_metrics(self, db) -> Dict[str, Any]:
        """Collect application-specific metrics (active sessions, users, etc)."""
        try:
            # Active exam sessions
            result = await db.execute(text("""
                SELECT count(*) as active_sessions
                FROM exam_sessions
                WHERE status = 'in_progress'
            """))
            active_sessions = result.scalar()

            # Total users by role
            result = await db.execute(text("""
                SELECT role, count(*) as count
                FROM users
                WHERE is_active = true
                GROUP BY role
            """))
            users_by_role = {row[0]: row[1] for row in result}

            # Published exams
            result = await db.execute(text("""
                SELECT count(*) as published_exams
                FROM exams
                WHERE is_published = true AND is_deleted = false
            """))
            published_exams = result.scalar()

            # Recent security events (last hour)
            result = await db.execute(text("""
                SELECT count(*) as recent_security_events
                FROM security_events
                WHERE timestamp > NOW() - INTERVAL '1 hour'
            """))
            recent_security_events = result.scalar()

            metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "sessions": {
                    "active": active_sessions
                },
                "users": users_by_role,
                "exams": {
                    "published": published_exams
                },
                "security": {
                    "recent_events": recent_security_events
                }
            }

            # Store in Redis
            if self.redis:
                await self.redis.setex(
                    "metrics:application:latest",
                    self.metrics_ttl,
                    json.dumps(metrics)
                )

            return metrics

        except Exception as e:
            logger.error(f"Error collecting application metrics: {e}")
            return {}

    async def collect_all_metrics(self, db) -> Dict[str, Any]:
        """Collect all metrics and return combined result."""
        now = datetime.utcnow()
        if (
            self._last_collected_at is not None
            and self._last_payload is not None
            and (now - self._last_collected_at).total_seconds() < self.min_refresh_seconds
        ):
            return self._last_payload

        system = await self.collect_system_metrics()
        database = await self.collect_database_metrics(db)
        redis_metrics = await self.collect_redis_metrics()
        application = await self.collect_application_metrics(db)

        payload = {
            "system": system,
            "database": database,
            "redis": redis_metrics,
            "application": application,
            "collected_at": now.isoformat()
        }

        self._last_collected_at = now
        self._last_payload = payload
        return payload

    async def get_latest_metrics(self) -> Dict[str, Any]:
        """Retrieve latest metrics from Redis."""
        try:
            if not self.redis:
                return {}

            system = await self.redis.get("metrics:system:latest")
            database = await self.redis.get("metrics:database:latest")
            redis_metrics = await self.redis.get("metrics:redis:latest")
            application = await self.redis.get("metrics:application:latest")

            def _decode(raw: Optional[str]) -> Dict[str, Any]:
                if not raw:
                    return {}
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON payload in cached metrics")
                    return {}

            return {
                "system": _decode(system),
                "database": _decode(database),
                "redis": _decode(redis_metrics),
                "application": _decode(application)
            }

        except Exception as e:
            logger.error(f"Error retrieving metrics: {e}")
            return {}


# Global metrics collector instance
metrics_collector = MetricsCollector()
