"""
Redis stream helpers for low-overhead monitoring delta feed.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.config import settings
from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)

STREAM_KEY_PREFIX = "monitoring:delta:exam"


def _stream_key(exam_id: int) -> str:
    return f"{STREAM_KEY_PREFIX}:{int(exam_id)}"


def _normalize_last_id(last_id: str) -> str:
    value = str(last_id or "").strip()
    if not value:
        return "0-0"
    if value.lower() in {"$", "latest"}:
        return "$"
    return value


async def publish_monitoring_delta(
    exam_id: int,
    event_type: str,
    payload: Dict[str, Any],
) -> str | None:
    """
    Publish compact monitor event into Redis Stream.

    Returns stream ID when published.
    """
    if not settings.monitoring_delta_stream_enabled:
        return None

    safe_payload = dict(payload or {})
    event = {
        "event_type": str(event_type or safe_payload.get("type") or "event"),
        "payload": safe_payload,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    key = _stream_key(exam_id)
    try:
        redis = await get_redis()
        stream_id = await redis.xadd(
            key,
            {"event": json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str)},
            maxlen=max(500, int(settings.monitoring_delta_stream_max_len)),
            approximate=True,
        )
        await redis.expire(key, max(300, int(settings.monitoring_delta_stream_ttl_seconds)))
        if isinstance(stream_id, bytes):
            return stream_id.decode("utf-8", errors="ignore")
        return str(stream_id)
    except Exception as exc:
        logger.debug("Failed to publish monitoring delta for exam=%s: %s", exam_id, exc)
        return None


async def read_monitoring_delta(
    exam_id: int,
    *,
    last_id: str = "0-0",
    limit: int = 200,
) -> Tuple[List[Dict[str, Any]], str]:
    """Read delta stream entries after last_id."""
    if not settings.monitoring_delta_stream_enabled:
        normalized = _normalize_last_id(last_id)
        return [], normalized if normalized != "$" else "0-0"

    count = max(1, min(1000, int(limit or 200)))
    normalized_last_id = _normalize_last_id(last_id)
    key = _stream_key(exam_id)

    try:
        redis = await get_redis()
        streams = await redis.xread({key: normalized_last_id}, count=count)
    except Exception as exc:
        logger.debug("Failed to read monitoring delta for exam=%s: %s", exam_id, exc)
        fallback_id = normalized_last_id if normalized_last_id != "$" else "0-0"
        return [], fallback_id

    if not streams:
        fallback_id = normalized_last_id if normalized_last_id != "$" else "0-0"
        return [], fallback_id

    entries: List[Dict[str, Any]] = []
    next_last_id = normalized_last_id if normalized_last_id != "$" else "0-0"
    for _, stream_entries in streams:
        for stream_id, fields in stream_entries:
            sid = stream_id.decode("utf-8", errors="ignore") if isinstance(stream_id, bytes) else str(stream_id)
            raw_event = fields.get("event")
            if isinstance(raw_event, bytes):
                raw_event = raw_event.decode("utf-8", errors="ignore")
            payload: Dict[str, Any] = {}
            try:
                loaded = json.loads(raw_event or "{}")
                if isinstance(loaded, dict):
                    payload = loaded
            except Exception:
                payload = {"event_type": "unknown", "payload": {}, "ts": None}

            payload["id"] = sid
            entries.append(payload)
            next_last_id = sid

    return entries, next_last_id
