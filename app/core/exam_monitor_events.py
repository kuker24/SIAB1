"""Shared helpers for publishing exam monitoring events.

Kept outside API routers so split exam modules can publish monitor updates without
importing each other and creating circular dependencies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.core.monitoring_delta import publish_monitoring_delta
from app.core.redis_pubsub import publish_message

logger = logging.getLogger(__name__)


async def publish_exam_monitor_event(exam_id: int, payload: Dict[str, Any]) -> None:
    """Publish an exam monitoring event and mirror it to the delta stream best-effort."""
    await publish_message(f"exam_monitor_{exam_id}", payload)
    try:
        await publish_monitoring_delta(
            exam_id=exam_id,
            event_type=str(payload.get("type") or "event"),
            payload=payload,
        )
    except Exception as delta_exc:
        logger.debug("Failed to mirror monitor event to delta stream: %s", str(delta_exc))
