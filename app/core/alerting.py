"""
Alerting System - Threshold-based monitoring and notifications.

Coverage:
- System resources (CPU, memory, disk)
- Runtime HTTP quality (5xx and p95 critical endpoints)
- Database pressure (connection usage, pool timeout spike)
- Redis pressure (blocked clients, timeout spike)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import psutil

from app.config import settings
from app.core.auto_restart import run_auto_restart_scheduler_tick
from app.core.auto_intelligence import run_auto_intelligence_tick
from app.core.metrics_collector import metrics_collector
from app.core.redis_pubsub import get_redis
from app.core.runtime_telemetry import (
    compute_endpoint_p95_latency_ms,
    compute_endpoint_p99_latency_ms,
    compute_lane_latency_percentile_ms,
    get_5xx_rate_percent,
    get_lane_5xx_rate_percent,
    get_runtime_event_rate,
)
from app.database import async_session_read
from app.utils.telegram_utils import send_telegram_notification

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertChannel(str, Enum):
    LOG = "log"
    DATABASE = "database"
    WEBHOOK = "webhook"  # Telegram/Slack style channel


class Alert:
    """Represents a triggered alert event."""

    def __init__(
        self,
        name: str,
        severity: AlertSeverity,
        message: str,
        metric_value: float,
        threshold: float,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.severity = severity
        self.message = message
        self.metric_value = metric_value
        self.threshold = threshold
        self.metadata = metadata or {}
        self.triggered_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity.value,
            "message": self.message,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "metadata": self.metadata,
            "triggered_at": self.triggered_at.isoformat(),
        }


class AlertRule:
    """Defines alert threshold, comparison, severity, and cooldown."""

    def __init__(
        self,
        name: str,
        metric_getter: Callable[[], Any],
        threshold: float,
        comparison: str = ">",
        severity: AlertSeverity = AlertSeverity.WARNING,
        message_template: Optional[str] = None,
        cooldown_minutes: int = 5,
        channels: Optional[List[AlertChannel]] = None,
    ):
        self.name = name
        self.metric_getter = metric_getter
        self.threshold = threshold
        self.comparison = comparison
        self.severity = severity
        self.message_template = message_template or f"{name} threshold breached"
        self.cooldown_minutes = cooldown_minutes
        self.channels = channels or [AlertChannel.LOG]
        self.last_triggered: Optional[datetime] = None

    async def evaluate(self) -> Optional[Alert]:
        """Evaluate current metric and return alert when threshold is breached."""
        try:
            metric_value = await self.metric_getter()

            if not self._check_threshold(metric_value):
                return None

            if self.last_triggered:
                elapsed = datetime.now(timezone.utc) - self.last_triggered
                if elapsed < timedelta(minutes=self.cooldown_minutes):
                    logger.debug("Alert %s is in cooldown", self.name)
                    return None

            message = self.message_template.format(
                value=metric_value,
                threshold=self.threshold,
            )
            alert = Alert(
                name=self.name,
                severity=self.severity,
                message=message,
                metric_value=float(metric_value),
                threshold=self.threshold,
            )
            self.last_triggered = datetime.now(timezone.utc)
            return alert
        except Exception as exc:
            logger.error("Error evaluating alert rule %s: %s", self.name, exc)
            return None

    def _check_threshold(self, value: float) -> bool:
        if self.comparison == ">":
            return value > self.threshold
        if self.comparison == "<":
            return value < self.threshold
        if self.comparison == ">=":
            return value >= self.threshold
        if self.comparison == "<=":
            return value <= self.threshold
        if self.comparison == "==":
            return value == self.threshold
        return False


class AlertingSystem:
    """Centralized monitoring and alert dispatch."""

    def __init__(self):
        self.rules: List[AlertRule] = []
        self.alert_handlers: Dict[AlertChannel, Callable] = {}
        self.is_running = False
        self.check_interval = 30  # seconds

        self.register_handler(AlertChannel.LOG, self._log_alert)
        self.register_handler(AlertChannel.DATABASE, self._store_alert_in_db)

        if settings.telegram_alerting_active and settings.telegram_bot_token and settings.telegram_chat_ids_list:
            self.register_handler(AlertChannel.WEBHOOK, self._send_webhook_alert)

    def add_rule(self, rule: AlertRule) -> None:
        self.rules.append(rule)
        logger.info("Added alert rule: %s", rule.name)

    def register_handler(self, channel: AlertChannel, handler: Callable) -> None:
        self.alert_handlers[channel] = handler

    async def start_monitoring(self) -> None:
        self.is_running = True
        logger.info("Alerting system started")
        while self.is_running:
            try:
                await self._check_all_rules()
                await asyncio.sleep(self.check_interval)
            except Exception as exc:
                logger.error("Error in alerting loop: %s", exc)
                await asyncio.sleep(self.check_interval)

    def stop_monitoring(self) -> None:
        self.is_running = False
        logger.info("Alerting system stopped")

    async def _check_all_rules(self) -> None:
        for rule in self.rules:
            alert = await rule.evaluate()
            if alert:
                await self._trigger_alert(alert, rule.channels)
        try:
            await run_auto_restart_scheduler_tick()
        except Exception as exc:
            logger.warning("Auto restart scheduler tick failed: %s", exc)
        try:
            await run_auto_intelligence_tick(
                force=False,
                source="alerting_loop",
                actor="alerting_system",
                reason="Periodic intelligent control tick from alerting loop",
            )
        except Exception as exc:
            logger.warning("Auto intelligence tick failed: %s", exc)

    async def _trigger_alert(self, alert: Alert, channels: List[AlertChannel]) -> None:
        logger.warning("ALERT TRIGGERED: %s - %s", alert.name, alert.message)

        for channel in channels:
            handler = self.alert_handlers.get(channel)
            if not handler:
                continue
            try:
                await handler(alert)
            except Exception as exc:
                logger.error("Error sending alert to %s: %s", channel, exc)

        if alert.severity == AlertSeverity.CRITICAL:
            logger.warning(
                "Critical alert observed (%s). Intelligent auto-healing will evaluate on scheduler tick.",
                alert.name,
            )

    async def _log_alert(self, alert: Alert) -> None:
        log_level = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.CRITICAL: logging.CRITICAL,
        }.get(alert.severity, logging.WARNING)
        logger.log(
            log_level,
            "[ALERT] %s: %s (value=%s, threshold=%s)",
            alert.name,
            alert.message,
            alert.metric_value,
            alert.threshold,
        )

    async def _store_alert_in_db(self, alert: Alert) -> None:
        """Store alert in Redis for quick lookup and history list."""
        try:
            payload = json.dumps(alert.to_dict())
            redis = await get_redis()
            key = f"alert:{alert.name}:{int(alert.triggered_at.timestamp())}"
            await redis.setex(key, 86400, payload)
            await redis.lpush("alerts:recent", payload)
            await redis.ltrim("alerts:recent", 0, 199)
        except Exception as exc:
            logger.error("Error storing alert payload: %s", exc)

    async def _send_webhook_alert(self, alert: Alert) -> None:
        """Telegram webhook-like alert dispatch."""
        ts = alert.triggered_at.astimezone(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S WIB")
        message = (
            f"🚨 *ALERT {alert.severity.value.upper()}*\n"
            f"*Rule:* `{alert.name}`\n"
            f"*Value:* `{alert.metric_value}`\n"
            f"*Threshold:* `{alert.threshold}`\n"
            f"*Time:* {ts}\n"
            f"*Message:* {alert.message}"
        )
        await send_telegram_notification(message, parse_mode="Markdown")

    async def get_recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            redis = await get_redis()
            alerts = await redis.lrange("alerts:recent", 0, max(0, limit - 1))
            parsed: List[Dict[str, Any]] = []
            for raw in alerts:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    parsed.append(json.loads(raw))
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed alert payload in alerts:recent")
            return parsed
        except Exception as exc:
            logger.error("Error fetching recent alerts: %s", exc)
            return []


async def get_cpu_usage() -> float:
    """Return a short averaged CPU sample for alerting.

    psutil.cpu_percent(interval=0.0) is an instantaneous delta sample and can
    intermittently report 100% inside containers even when sustained CPU is low.
    Use a short threaded sample so the alerting loop stays non-blocking and the
    critical CPU alert is based on real sustained pressure, not a one-tick spike.
    """
    return float(await asyncio.to_thread(psutil.cpu_percent, interval=0.25))


async def get_memory_usage() -> float:
    return float(psutil.virtual_memory().percent)


async def get_disk_usage() -> float:
    return float(psutil.disk_usage("/").percent)


async def get_db_connection_usage_percent() -> float:
    await metrics_collector.initialize()
    async with async_session_read() as db:
        metrics = await metrics_collector.collect_database_metrics(db)
    return float(metrics.get("connections", {}).get("percent_used", 0.0))


async def get_redis_blocked_clients() -> float:
    redis = await get_redis()
    info = await redis.info()
    return float(info.get("blocked_clients", 0))


async def get_http_5xx_rate() -> float:
    return float(await get_5xx_rate_percent(window_seconds=60))


async def get_login_p95_latency() -> float:
    return float(await compute_endpoint_p95_latency_ms("auth_signin", window_seconds=180))


async def get_exam_start_p95_latency() -> float:
    return float(await compute_endpoint_p95_latency_ms("exam_start", window_seconds=180))


async def get_submit_answer_p95_latency() -> float:
    return float(await compute_endpoint_p95_latency_ms("submit_answer", window_seconds=180))


async def get_submit_answer_p99_latency() -> float:
    return float(await compute_endpoint_p99_latency_ms("submit_answer", window_seconds=180))


async def get_student_lane_p99_latency() -> float:
    return float(
        await compute_lane_latency_percentile_ms(
            "student",
            percentile=0.99,
            window_seconds=180,
        )
    )


async def get_admin_lane_p99_latency() -> float:
    return float(
        await compute_lane_latency_percentile_ms(
            "admin",
            percentile=0.99,
            window_seconds=180,
        )
    )


async def get_student_lane_5xx_rate() -> float:
    return float(await get_lane_5xx_rate_percent("student", window_seconds=60))


async def get_admin_lane_5xx_rate() -> float:
    return float(await get_lane_5xx_rate_percent("admin", window_seconds=60))


async def get_db_pool_timeout_event_rate() -> float:
    return float(await get_runtime_event_rate("db_pool_timeout", window_seconds=60))


async def get_redis_timeout_event_rate() -> float:
    return float(await get_runtime_event_rate("redis_timeout", window_seconds=60))


CPU_HIGH_ALERT = AlertRule(
    name="cpu_usage_high",
    metric_getter=get_cpu_usage,
    threshold=80,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="High CPU usage detected: {value:.1f}% (threshold: {threshold}%)",
    cooldown_minutes=5,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

CPU_CRITICAL_ALERT = AlertRule(
    name="cpu_usage_critical",
    metric_getter=get_cpu_usage,
    threshold=95,
    comparison=">",
    severity=AlertSeverity.CRITICAL,
    message_template="CRITICAL CPU usage: {value:.1f}% (threshold: {threshold}%)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE, AlertChannel.WEBHOOK],
)

MEMORY_HIGH_ALERT = AlertRule(
    name="memory_usage_high",
    metric_getter=get_memory_usage,
    threshold=85,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="High memory usage detected: {value:.1f}% (threshold: {threshold}%)",
    cooldown_minutes=5,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

MEMORY_CRITICAL_ALERT = AlertRule(
    name="memory_usage_critical",
    metric_getter=get_memory_usage,
    threshold=95,
    comparison=">",
    severity=AlertSeverity.CRITICAL,
    message_template="CRITICAL memory usage: {value:.1f}% (threshold: {threshold}%)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE, AlertChannel.WEBHOOK],
)

DISK_HIGH_ALERT = AlertRule(
    name="disk_usage_high",
    metric_getter=get_disk_usage,
    threshold=90,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Low disk headroom: {value:.1f}% used (threshold: {threshold}%)",
    cooldown_minutes=15,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

DISK_CRITICAL_ALERT = AlertRule(
    name="disk_usage_critical",
    metric_getter=get_disk_usage,
    threshold=95,
    comparison=">",
    severity=AlertSeverity.CRITICAL,
    message_template="CRITICAL disk usage: {value:.1f}% (threshold: {threshold}%)",
    cooldown_minutes=5,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE, AlertChannel.WEBHOOK],
)

HTTP_5XX_WARNING_ALERT = AlertRule(
    name="http_5xx_rate_warning",
    metric_getter=get_http_5xx_rate,
    threshold=1.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="HTTP 5xx rate high: {value:.2f}% (threshold: {threshold}%)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

HTTP_5XX_CRITICAL_ALERT = AlertRule(
    name="http_5xx_rate_critical",
    metric_getter=get_http_5xx_rate,
    threshold=3.0,
    comparison=">",
    severity=AlertSeverity.CRITICAL,
    message_template="CRITICAL HTTP 5xx rate: {value:.2f}% (threshold: {threshold}%)",
    cooldown_minutes=1,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE, AlertChannel.WEBHOOK],
)

LOGIN_P95_WARNING_ALERT = AlertRule(
    name="login_p95_latency_warning",
    metric_getter=get_login_p95_latency,
    threshold=1500.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Login p95 latency high: {value:.0f}ms (threshold: {threshold}ms)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

EXAM_START_P95_WARNING_ALERT = AlertRule(
    name="exam_start_p95_latency_warning",
    metric_getter=get_exam_start_p95_latency,
    threshold=2000.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Exam start p95 latency high: {value:.0f}ms (threshold: {threshold}ms)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

SUBMIT_ANSWER_P95_WARNING_ALERT = AlertRule(
    name="submit_answer_p95_latency_warning",
    metric_getter=get_submit_answer_p95_latency,
    threshold=1500.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Submit-answer p95 latency high: {value:.0f}ms (threshold: {threshold}ms)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

SUBMIT_ANSWER_P99_WARNING_ALERT = AlertRule(
    name="submit_answer_p99_latency_warning",
    metric_getter=get_submit_answer_p99_latency,
    threshold=2800.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Submit-answer p99 latency high: {value:.0f}ms (threshold: {threshold}ms)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

STUDENT_LANE_P99_WARNING_ALERT = AlertRule(
    name="student_lane_p99_latency_warning",
    metric_getter=get_student_lane_p99_latency,
    threshold=2600.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Student lane p99 latency high: {value:.0f}ms (threshold: {threshold}ms)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

STUDENT_LANE_P99_CRITICAL_ALERT = AlertRule(
    name="student_lane_p99_latency_critical",
    metric_getter=get_student_lane_p99_latency,
    threshold=4500.0,
    comparison=">",
    severity=AlertSeverity.CRITICAL,
    message_template="CRITICAL student lane p99 latency: {value:.0f}ms (threshold: {threshold}ms)",
    cooldown_minutes=1,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE, AlertChannel.WEBHOOK],
)

ADMIN_LANE_P99_WARNING_ALERT = AlertRule(
    name="admin_lane_p99_latency_warning",
    metric_getter=get_admin_lane_p99_latency,
    threshold=3500.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Admin lane p99 latency high: {value:.0f}ms (threshold: {threshold}ms)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

ADMIN_LANE_5XX_WARNING_ALERT = AlertRule(
    name="admin_lane_5xx_rate_warning",
    metric_getter=get_admin_lane_5xx_rate,
    threshold=2.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Admin lane 5xx rate high: {value:.2f}% (threshold: {threshold}%)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

STUDENT_LANE_5XX_WARNING_ALERT = AlertRule(
    name="student_lane_5xx_rate_warning",
    metric_getter=get_student_lane_5xx_rate,
    threshold=1.2,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Student lane 5xx rate high: {value:.2f}% (threshold: {threshold}%)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

DB_CONNECTION_USAGE_WARNING_ALERT = AlertRule(
    name="db_connection_usage_warning",
    metric_getter=get_db_connection_usage_percent,
    threshold=85.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="DB connection usage high: {value:.1f}% (threshold: {threshold}%)",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

DB_CONNECTION_USAGE_CRITICAL_ALERT = AlertRule(
    name="db_connection_usage_critical",
    metric_getter=get_db_connection_usage_percent,
    threshold=95.0,
    comparison=">",
    severity=AlertSeverity.CRITICAL,
    message_template="CRITICAL DB connection usage: {value:.1f}% (threshold: {threshold}%)",
    cooldown_minutes=1,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE, AlertChannel.WEBHOOK],
)

REDIS_BLOCKED_CLIENTS_ALERT = AlertRule(
    name="redis_blocked_clients_high",
    metric_getter=get_redis_blocked_clients,
    threshold=10.0,
    comparison=">",
    severity=AlertSeverity.WARNING,
    message_template="Redis blocked clients high: {value:.0f} (threshold: {threshold})",
    cooldown_minutes=2,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
)

DB_POOL_TIMEOUT_EVENT_ALERT = AlertRule(
    name="db_pool_timeout_event_spike",
    metric_getter=get_db_pool_timeout_event_rate,
    threshold=1.0,
    comparison=">",
    severity=AlertSeverity.CRITICAL,
    message_template="DB pool timeout spike: {value:.2f} events/min (threshold: {threshold})",
    cooldown_minutes=1,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE, AlertChannel.WEBHOOK],
)

REDIS_TIMEOUT_EVENT_ALERT = AlertRule(
    name="redis_timeout_event_spike",
    metric_getter=get_redis_timeout_event_rate,
    threshold=1.0,
    comparison=">",
    severity=AlertSeverity.CRITICAL,
    message_template="Redis timeout spike: {value:.2f} events/min (threshold: {threshold})",
    cooldown_minutes=1,
    channels=[AlertChannel.LOG, AlertChannel.DATABASE, AlertChannel.WEBHOOK],
)


alerting_system = AlertingSystem()

for rule in [
    CPU_HIGH_ALERT,
    CPU_CRITICAL_ALERT,
    MEMORY_HIGH_ALERT,
    MEMORY_CRITICAL_ALERT,
    DISK_HIGH_ALERT,
    DISK_CRITICAL_ALERT,
    HTTP_5XX_WARNING_ALERT,
    HTTP_5XX_CRITICAL_ALERT,
    LOGIN_P95_WARNING_ALERT,
    EXAM_START_P95_WARNING_ALERT,
    SUBMIT_ANSWER_P95_WARNING_ALERT,
    SUBMIT_ANSWER_P99_WARNING_ALERT,
    STUDENT_LANE_P99_WARNING_ALERT,
    STUDENT_LANE_P99_CRITICAL_ALERT,
    ADMIN_LANE_P99_WARNING_ALERT,
    STUDENT_LANE_5XX_WARNING_ALERT,
    ADMIN_LANE_5XX_WARNING_ALERT,
    DB_CONNECTION_USAGE_WARNING_ALERT,
    DB_CONNECTION_USAGE_CRITICAL_ALERT,
    REDIS_BLOCKED_CLIENTS_ALERT,
    DB_POOL_TIMEOUT_EVENT_ALERT,
    REDIS_TIMEOUT_EVENT_ALERT,
]:
    alerting_system.add_rule(rule)
