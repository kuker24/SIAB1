"""
Alerts API - View and manage system alerts
"""
from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from app.core.security import get_current_active_admin
from app.models.user import User
from app.core.alerting import alerting_system
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/alerts", tags=["alerts"])


@router.get("/recent")
async def get_recent_alerts(
    limit: int = 20,
    current_user: User = Depends(get_current_active_admin)
) -> List[Dict[str, Any]]:
    """Get recent triggered alerts."""
    alerts = await alerting_system.get_recent_alerts(limit=limit)
    return alerts


@router.get("/rules")
async def get_alert_rules(
    current_user: User = Depends(get_current_active_admin)
) -> List[Dict[str, Any]]:
    """Get all configured alert rules."""
    rules = []
    for rule in alerting_system.rules:
        rules.append({
            "name": rule.name,
            "threshold": rule.threshold,
            "comparison": rule.comparison,
            "severity": rule.severity.value,
            "cooldown_minutes": rule.cooldown_minutes,
            "channels": [ch.value for ch in rule.channels]
        })
    return rules


@router.get("/status")
async def get_alerting_status(
    current_user: User = Depends(get_current_active_admin)
) -> Dict[str, Any]:
    """Get alerting system status."""
    return {
        "is_running": alerting_system.is_running,
        "check_interval_seconds": alerting_system.check_interval,
        "active_rules_count": len(alerting_system.rules),
        "registered_handlers": list(alerting_system.alert_handlers.keys())
    }
