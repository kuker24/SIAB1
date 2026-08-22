"""
Intelligent auto-performance mode and auto-healing orchestration.

Goals:
- Keep exam-critical flows stable under pressure.
- Switch resource mode (normal/high/extreme) automatically with hysteresis.
- Trigger safe backend API self-healing actions when needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.degrade_mode import set_degrade_mode, set_resource_mode
from app.core.ops_summary import get_ops_summary, invalidate_ops_summary_cache
from app.core.redis_pubsub import get_redis
from app.database import async_session_read

logger = logging.getLogger(__name__)


AUTO_INTELLIGENCE_STATE_KEY = "system:auto_intelligence_state"
AUTO_INTELLIGENCE_LOCK_KEY = "system:auto_intelligence_tick_lock"

MODE_RANK = {"normal": 0, "high": 1, "extreme": 2}


# In-process cache to reduce Redis round-trips for bursty dashboard polling.
_cached_state: Optional[Dict[str, Any]] = None
_cached_at_monotonic: float = 0.0
CACHE_TTL_SECONDS = 3.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _seconds_since(value: Optional[str]) -> Optional[float]:
    parsed = _parse_iso(value)
    if not parsed:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _resolve_default_ops_host_header() -> str:
    configured_public_base = str(getattr(settings, "monitor_public_base_url", "") or "").strip()
    if configured_public_base:
        configured_url = (
            configured_public_base
            if "://" in configured_public_base
            else f"https://{configured_public_base}"
        )
        parsed = urlparse(configured_url)
        if parsed.netloc:
            return parsed.netloc

    for origin in getattr(settings, "cors_origins_list", []):
        origin_value = str(origin or "").strip()
        if not origin_value:
            continue
        origin_url = origin_value if "://" in origin_value else f"https://{origin_value}"
        parsed_origin = urlparse(origin_url)
        if parsed_origin.netloc:
            return parsed_origin.netloc

    configured_domain = str(getattr(settings, "domain", "") or "").strip()
    if not configured_domain:
        return ""
    if "://" in configured_domain:
        parsed_domain = urlparse(configured_domain)
        return (parsed_domain.netloc or "").strip()
    return configured_domain.split("/", 1)[0].strip()


def _default_state() -> Dict[str, Any]:
    return {
        "controls": {
            "auto_mode_enabled": bool(
                os.getenv("AUTO_INTELLIGENCE_MODE_DEFAULT_ENABLED", "true").strip().lower() == "true"
            ),
            "auto_heal_enabled": bool(
                os.getenv("AUTO_INTELLIGENCE_HEAL_DEFAULT_ENABLED", "true").strip().lower() == "true"
            ),
            "updated_at": None,
            "source": "default",
            "actor": None,
            "reason": "Default auto intelligence policy",
        },
        "runtime": {
            "current_mode": "normal",
            "last_tick_at": None,
            "last_tick_source": None,
            "last_mode_change_at": None,
            "consecutive_pressure_cycles": 0,
            "consecutive_relief_cycles": 0,
            "last_mode_decision": {
                "target_mode": "normal",
                "score": 0.0,
                "confidence": 0.0,
                "signals": [],
                "reasons": ["Belum ada evaluasi"],
            },
            "last_mode_action": {
                "changed": False,
                "from_mode": "normal",
                "to_mode": "normal",
                "reason": "Belum ada perubahan mode",
                "at": None,
            },
            "last_heal": {
                "status": "idle",
                "executed": False,
                "summary": "Belum ada aksi auto healing",
                "reason": None,
                "at": None,
                "cooldown_remaining_seconds": 0,
                "actions": [],
            },
        },
        "updated_at": None,
    }


def _deep_merge(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in incoming.items():
        if isinstance(base.get(key), dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _normalize_state(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    state = _default_state()
    if isinstance(payload, dict):
        _deep_merge(state, payload)

    controls = state.get("controls") or {}
    controls["auto_mode_enabled"] = bool(controls.get("auto_mode_enabled", True))
    controls["auto_heal_enabled"] = bool(controls.get("auto_heal_enabled", True))

    runtime = state.get("runtime") or {}
    current_mode = str(runtime.get("current_mode") or "normal").lower()
    if current_mode not in MODE_RANK:
        current_mode = "normal"
    runtime["current_mode"] = current_mode
    runtime["consecutive_pressure_cycles"] = max(0, _safe_int(runtime.get("consecutive_pressure_cycles"), 0))
    runtime["consecutive_relief_cycles"] = max(0, _safe_int(runtime.get("consecutive_relief_cycles"), 0))

    last_decision = runtime.get("last_mode_decision")
    if not isinstance(last_decision, dict):
        runtime["last_mode_decision"] = {
            "target_mode": current_mode,
            "score": 0.0,
            "confidence": 0.0,
            "signals": [],
            "reasons": ["Belum ada evaluasi"],
        }

    last_mode_action = runtime.get("last_mode_action")
    if not isinstance(last_mode_action, dict):
        runtime["last_mode_action"] = {
            "changed": False,
            "from_mode": current_mode,
            "to_mode": current_mode,
            "reason": "Belum ada perubahan mode",
            "at": None,
        }

    last_heal = runtime.get("last_heal")
    if not isinstance(last_heal, dict):
        runtime["last_heal"] = {
            "status": "idle",
            "executed": False,
            "summary": "Belum ada aksi auto healing",
            "reason": None,
            "at": None,
            "cooldown_remaining_seconds": 0,
            "actions": [],
        }

    state["controls"] = controls
    state["runtime"] = runtime
    return state


async def _persist_state(state: Dict[str, Any]) -> None:
    global _cached_state, _cached_at_monotonic
    normalized = _normalize_state(state)
    normalized["updated_at"] = _now_iso()

    try:
        redis = await get_redis()
        await redis.set(AUTO_INTELLIGENCE_STATE_KEY, json.dumps(normalized))
    except Exception as exc:
        logger.warning("Failed to persist auto intelligence state: %s", exc)

    _cached_state = normalized
    _cached_at_monotonic = asyncio.get_running_loop().time()


async def get_auto_intelligence_state(force_refresh: bool = False) -> Dict[str, Any]:
    global _cached_state, _cached_at_monotonic

    loop = asyncio.get_running_loop()
    if (
        not force_refresh
        and _cached_state is not None
        and (loop.time() - _cached_at_monotonic) < CACHE_TTL_SECONDS
    ):
        return _normalize_state(dict(_cached_state))

    try:
        redis = await get_redis()
        raw = await redis.get(AUTO_INTELLIGENCE_STATE_KEY)
        if not raw:
            state = _normalize_state(None)
            await _persist_state(state)
            return state

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        payload = json.loads(raw)
        state = _normalize_state(payload if isinstance(payload, dict) else None)
        _cached_state = state
        _cached_at_monotonic = loop.time()
        return state
    except Exception as exc:
        logger.warning("Failed to load auto intelligence state: %s", exc)
        state = _normalize_state(None)
        _cached_state = state
        _cached_at_monotonic = loop.time()
        return state


async def update_auto_intelligence_controls(
    *,
    auto_mode_enabled: Optional[bool] = None,
    auto_heal_enabled: Optional[bool] = None,
    actor: Optional[str] = None,
    source: str = "manual",
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    state = await get_auto_intelligence_state(force_refresh=True)
    controls = state.get("controls") or {}

    if auto_mode_enabled is not None:
        controls["auto_mode_enabled"] = bool(auto_mode_enabled)
    if auto_heal_enabled is not None:
        controls["auto_heal_enabled"] = bool(auto_heal_enabled)

    controls["updated_at"] = _now_iso()
    controls["source"] = source
    controls["actor"] = actor
    controls["reason"] = reason or "Control update"
    state["controls"] = controls

    await _persist_state(state)
    return _normalize_state(state)


async def _acquire_tick_lock(lock_seconds: int = 25) -> Optional[str]:
    token = uuid.uuid4().hex
    try:
        redis = await get_redis()
        acquired = await redis.set(AUTO_INTELLIGENCE_LOCK_KEY, token, nx=True, ex=max(5, lock_seconds))
        if acquired:
            return token
    except Exception as exc:
        logger.warning("Failed to acquire auto intelligence lock: %s", exc)
    return None


async def _release_tick_lock(token: Optional[str]) -> None:
    if not token:
        return
    try:
        redis = await get_redis()
        current = await redis.get(AUTO_INTELLIGENCE_LOCK_KEY)
        if isinstance(current, bytes):
            current = current.decode("utf-8", errors="ignore")
        if current == token:
            await redis.delete(AUTO_INTELLIGENCE_LOCK_KEY)
    except Exception as exc:
        logger.warning("Failed to release auto intelligence lock: %s", exc)


def _layer_lookup(summary: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for layer in summary.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        layer_id = str(layer.get("id") or "").strip().lower()
        if layer_id:
            lookup[layer_id] = layer
    return lookup


def _compute_mode_decision(
    summary: Dict[str, Any],
    *,
    current_mode: str,
    consecutive_relief_cycles: int,
) -> Dict[str, Any]:
    key_metrics = summary.get("key_metrics") or {}
    activity = summary.get("activity") or {}
    layers = _layer_lookup(summary)

    global_5xx = _safe_float(key_metrics.get("global_5xx_percent"), 0.0)
    auth_p95 = _safe_float(key_metrics.get("auth_signin_p95_ms"), 0.0)
    exam_start_p95 = _safe_float(key_metrics.get("exam_start_p95_ms"), 0.0)
    submit_p95 = _safe_float(key_metrics.get("submit_answer_p95_ms"), 0.0)
    max_p95 = max(auth_p95, exam_start_p95, submit_p95)

    cpu = _safe_float(key_metrics.get("cpu_percent"), 0.0)
    db_conn = _safe_float(key_metrics.get("db_connection_percent"), 0.0)
    redis_stability = _safe_float(key_metrics.get("redis_stability_score_percent"), 100.0)
    active_sessions = max(0, _safe_int(activity.get("active_sessions"), 0))

    backend_status = str((layers.get("backend_api") or {}).get("status") or "unknown").lower()
    db_status = str((layers.get("database") or {}).get("status") or "unknown").lower()
    redis_status = str((layers.get("redis") or {}).get("status") or "unknown").lower()

    warning_count = 0
    critical_count = 0
    for layer in summary.get("layers") or []:
        status = str((layer or {}).get("status") or "unknown").lower()
        if status == "warning":
            warning_count += 1
        elif status == "critical":
            critical_count += 1

    score = 0.0
    signals: List[str] = []

    if global_5xx > 0.0:
        contribution = min(34.0, global_5xx * 8.2)
        score += contribution
        if global_5xx >= 1.0:
            signals.append(f"5xx {global_5xx:.2f}%")

    if max_p95 > 1_200:
        contribution = min(26.0, (max_p95 - 1_200.0) / 110.0)
        score += contribution
        if max_p95 >= 2_500:
            signals.append(f"p95 {max_p95:.0f}ms")

    if cpu > 78:
        contribution = min(14.0, (cpu - 78.0) * 0.6)
        score += contribution
        if cpu >= 90:
            signals.append(f"CPU {cpu:.1f}%")

    if db_conn > 82:
        contribution = min(18.0, (db_conn - 82.0) * 0.95)
        score += contribution
        if db_conn >= 92:
            signals.append(f"DB conn {db_conn:.1f}%")

    if redis_stability < 96:
        contribution = min(22.0, max(0.0, 100.0 - redis_stability) * 0.4)
        score += contribution
        if redis_stability <= 92:
            signals.append(f"Redis stability {redis_stability:.1f}%")

    score += (warning_count * 3.0) + (critical_count * 8.0)

    if backend_status == "critical":
        score += 16.0
        signals.append("Backend API critical")
    elif backend_status == "warning":
        score += 6.0

    if db_status == "critical":
        score += 10.0
        signals.append("Database critical")

    if redis_status == "critical":
        score += 8.0
        signals.append("Redis critical")

    if active_sessions >= 800:
        score += 4.0
        signals.append(f"Sesi aktif {active_sessions}")
    elif active_sessions >= 400:
        score += 3.0
        signals.append(f"Sesi aktif {active_sessions}")
    elif active_sessions >= 200:
        score += 2.0
        signals.append(f"Sesi aktif {active_sessions}")
    elif active_sessions >= 50:
        score += 1.0

    score = round(_clamp(score, 0.0, 100.0), 2)

    # Dynamic threshold intentionally conservative:
    # keep NORMAL as long as system remains serviceable.
    if active_sessions >= 800:
        high_threshold = 54.0
        extreme_threshold = 84.0
    elif active_sessions >= 400:
        high_threshold = 52.0
        extreme_threshold = 82.0
    elif active_sessions >= 200:
        high_threshold = 48.0
        extreme_threshold = 80.0
    elif active_sessions >= 50:
        high_threshold = 45.0
        extreme_threshold = 78.0
    else:
        high_threshold = 42.0
        extreme_threshold = 75.0

    target_mode = "normal"
    if score >= extreme_threshold:
        target_mode = "extreme"
    elif score >= high_threshold:
        target_mode = "high"

    if backend_status == "critical" and (global_5xx >= 2.5 or max_p95 >= 3200):
        target_mode = "extreme"
    elif backend_status == "critical" and target_mode == "normal" and (global_5xx >= 1.0 or max_p95 >= 2200):
        target_mode = "high"
    elif backend_status == "warning" and target_mode == "normal" and (global_5xx >= 1.5 or max_p95 >= 2600):
        target_mode = "high"

    if critical_count >= 4:
        target_mode = "extreme"

    # Confidence blends signal count and distance from threshold boundary.
    signal_density = _clamp(len(set(signals)) / 7.0, 0.0, 1.0)
    if target_mode == "extreme":
        margin = _clamp((score - extreme_threshold) / max(5.0, (100.0 - extreme_threshold)), 0.0, 1.0)
    elif target_mode == "high":
        high_span = max(6.0, extreme_threshold - high_threshold)
        left = _clamp((score - high_threshold) / high_span, 0.0, 1.0)
        right = _clamp((extreme_threshold - score) / high_span, 0.0, 1.0)
        margin = min(left, right) if score < extreme_threshold else left
    else:
        margin = _clamp((high_threshold - score) / max(10.0, high_threshold), 0.0, 1.0)

    confidence = 0.38 + (signal_density * 0.4) + (margin * 0.22)
    if active_sessions > 0 and target_mode != "normal":
        confidence += 0.04
    confidence = round(_clamp(confidence, 0.33, 0.97), 3)

    current_rank = MODE_RANK.get(current_mode, 0)
    target_rank = MODE_RANK.get(target_mode, 0)
    direction = "steady"
    if target_rank > current_rank:
        direction = "up"
    elif target_rank < current_rank:
        direction = "down"

    reasons: List[str] = []
    if target_mode == "extreme":
        reasons.append("Tekanan sistem tinggi, prioritas penuh ke stabilitas ujian")
    elif target_mode == "high":
        reasons.append("Ada tekanan menengah, fitur non-kritis diperlambat")
    else:
        reasons.append("Sistem stabil, mode normal dipertahankan")

    if backend_status in {"warning", "critical"}:
        reasons.append("Backend API menunjukkan degradasi")
    if global_5xx >= 1.0:
        reasons.append(f"Rasio 5xx {global_5xx:.2f}%")
    if max_p95 >= 1800:
        reasons.append(f"Latency p95 endpoint kritikal {max_p95:.0f}ms")
    if active_sessions > 0:
        reasons.append(f"Sesi aktif saat ini {active_sessions}")
    if direction == "down" and consecutive_relief_cycles < 2:
        reasons.append("Menahan downgrade sementara (hysteresis)")

    return {
        "current_mode": current_mode,
        "target_mode": target_mode,
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "signals": sorted(set(signals)),
        "reasons": reasons,
        "active_sessions": active_sessions,
        "thresholds": {
            "high": high_threshold,
            "extreme": extreme_threshold,
        },
    }


def _should_allow_downgrade(
    *,
    current_mode: str,
    target_mode: str,
    decision: Dict[str, Any],
    consecutive_relief_cycles: int,
    cooldown_over: bool,
    confidence: float,
) -> bool:
    """
    Allow downgrade aggressively enough to avoid mode lock, but still bounded.

    The old logic could keep system stuck in high/extreme when confidence stayed
    slightly below threshold despite many consecutive relief cycles.
    """
    current_rank = MODE_RANK.get(current_mode, 0)
    target_rank = MODE_RANK.get(target_mode, 0)
    if target_rank >= current_rank or not cooldown_over:
        return False

    score = _safe_float(decision.get("score"), 0.0)
    thresholds = decision.get("thresholds") or {}
    high_threshold = _safe_float(thresholds.get("high"), 45.0)

    minimum_confidence = 0.50 if target_mode == "normal" else 0.56
    if consecutive_relief_cycles >= 2 and confidence >= minimum_confidence:
        return True

    # Strong relief for several cycles should release from high/extreme lock even
    # when confidence stays moderate (for example noisy layer warning telemetry).
    if target_mode == "normal" and consecutive_relief_cycles >= 5 and score <= max(0.0, high_threshold - 4.0):
        return True

    # Hard safety net: never keep elevated mode forever when relief is persistent.
    if consecutive_relief_cycles >= 10:
        return True

    return False


def _resolve_heal_command() -> Tuple[Optional[List[str]], Optional[str]]:
    configured = str(os.getenv("AUTO_INTELLIGENCE_HEAL_COMMAND", "") or "").strip()
    if configured:
        try:
            command = shlex.split(configured)
            if command:
                return command, "env: AUTO_INTELLIGENCE_HEAL_COMMAND"
        except ValueError as exc:
            logger.warning("Invalid AUTO_INTELLIGENCE_HEAL_COMMAND: %s", exc)

    candidates = [
        os.path.join(os.getcwd(), "scripts", "autoheal_unhealthy_apis.sh"),
        "/app/scripts/autoheal_unhealthy_apis.sh",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return ["/usr/bin/env", "bash", path], f"file: {path}"

    return None, None


async def _run_heal_command(command: List[str], timeout_seconds: int) -> Dict[str, Any]:
    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

    result = await asyncio.to_thread(_run)
    return {
        "returncode": int(result.returncode),
        "stdout_tail": (result.stdout or "").splitlines()[-20:],
        "stderr_tail": (result.stderr or "").splitlines()[-20:],
    }


def _need_healing(summary: Dict[str, Any], force_heal: bool = False) -> Tuple[bool, str]:
    if force_heal:
        return True, "manual_force_heal"

    key_metrics = summary.get("key_metrics") or {}
    layers = _layer_lookup(summary)

    backend_layer = layers.get("backend_api") or {}
    backend_status = str(backend_layer.get("status") or "unknown").lower()
    backend_metrics = backend_layer.get("metrics") or {}

    global_5xx = _safe_float(key_metrics.get("global_5xx_percent"), 0.0)
    max_p95 = max(
        _safe_float(key_metrics.get("auth_signin_p95_ms"), 0.0),
        _safe_float(key_metrics.get("exam_start_p95_ms"), 0.0),
        _safe_float(key_metrics.get("submit_answer_p95_ms"), 0.0),
    )
    origin_status = _safe_int(backend_metrics.get("origin_status_code"), 0)

    if backend_status == "critical":
        return True, "backend_api_critical"

    if backend_status == "warning" and (global_5xx >= 1.5 or max_p95 >= 2400 or origin_status >= 500):
        return True, "backend_api_warning_with_runtime_pressure"

    if global_5xx >= 4.0:
        return True, "global_5xx_critical"

    return False, "no_heal_signal"


async def run_auto_intelligence_tick(
    *,
    host_header: str = "",
    db: Optional[AsyncSession] = None,
    summary: Optional[Dict[str, Any]] = None,
    force: bool = False,
    force_heal: bool = False,
    source: str = "scheduler",
    actor: str = "auto_intelligence",
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    effective_host_header = (host_header or "").strip() or _resolve_default_ops_host_header()
    state = await get_auto_intelligence_state(force_refresh=False)
    controls = state.get("controls") or {}
    runtime = state.get("runtime") or {}

    min_tick_seconds = int(_clamp(_safe_float(os.getenv("AUTO_INTELLIGENCE_MIN_TICK_SECONDS", "20"), 20.0), 5.0, 300.0))
    mode_cooldown_seconds = int(
        _clamp(_safe_float(os.getenv("AUTO_INTELLIGENCE_MODE_COOLDOWN_SECONDS", "90"), 90.0), 20.0, 1200.0)
    )
    upgrade_min_cycles_high = int(
        _clamp(_safe_float(os.getenv("AUTO_INTELLIGENCE_UPGRADE_MIN_CYCLES_HIGH", "2"), 2.0), 1.0, 12.0)
    )
    upgrade_min_cycles_extreme = int(
        _clamp(_safe_float(os.getenv("AUTO_INTELLIGENCE_UPGRADE_MIN_CYCLES_EXTREME", "3"), 3.0), 1.0, 20.0)
    )
    heal_cooldown_seconds = int(
        _clamp(_safe_float(os.getenv("AUTO_INTELLIGENCE_HEAL_COOLDOWN_SECONDS", "180"), 180.0), 30.0, 1800.0)
    )
    mode_ttl_minutes = int(
        _clamp(_safe_float(os.getenv("AUTO_INTELLIGENCE_MODE_TTL_MINUTES", "180"), 180.0), 15.0, 24.0 * 60.0)
    )
    heal_timeout_seconds = int(
        _clamp(_safe_float(os.getenv("AUTO_INTELLIGENCE_HEAL_TIMEOUT_SECONDS", "90"), 90.0), 15.0, 600.0)
    )

    now_iso = _now_iso()
    now_tick_age = _seconds_since(runtime.get("last_tick_at"))
    if not force and now_tick_age is not None and now_tick_age < float(min_tick_seconds):
        remaining = int(max(0.0, float(min_tick_seconds) - now_tick_age))
        last_decision = runtime.get("last_mode_decision") or {}
        last_heal = runtime.get("last_heal") or {}
        return {
            "executed": False,
            "skipped": "tick_interval",
            "cooldown_remaining_seconds": remaining,
            "controls": {
                "auto_mode_enabled": bool(controls.get("auto_mode_enabled", True)),
                "auto_heal_enabled": bool(controls.get("auto_heal_enabled", True)),
            },
            "mode": {
                "changed": False,
                "decision": last_decision,
                "action": runtime.get("last_mode_action") or {},
            },
            "healing": last_heal,
            "timestamp": now_iso,
        }

    lock_token = await _acquire_tick_lock()
    if not lock_token:
        last_decision = runtime.get("last_mode_decision") or {}
        return {
            "executed": False,
            "skipped": "lock_busy",
            "controls": {
                "auto_mode_enabled": bool(controls.get("auto_mode_enabled", True)),
                "auto_heal_enabled": bool(controls.get("auto_heal_enabled", True)),
            },
            "mode": {
                "changed": False,
                "decision": last_decision,
                "action": runtime.get("last_mode_action") or {},
            },
            "healing": runtime.get("last_heal") or {},
            "timestamp": now_iso,
        }

    try:
        working_summary: Optional[Dict[str, Any]] = summary if isinstance(summary, dict) else None
        if working_summary is None:
            if db is not None:
                working_summary = await get_ops_summary(host_header=effective_host_header, db=db)
            else:
                async with async_session_read() as db_read:
                    working_summary = await get_ops_summary(host_header=effective_host_header, db=db_read)

        if not isinstance(working_summary, dict):
            raise RuntimeError("ops summary unavailable")

        current_mode = str((working_summary.get("policy") or {}).get("resource_mode") or runtime.get("current_mode") or "normal").lower()
        if current_mode not in MODE_RANK:
            current_mode = "normal"

        consecutive_pressure_cycles = max(0, _safe_int(runtime.get("consecutive_pressure_cycles"), 0))
        consecutive_relief_cycles = max(0, _safe_int(runtime.get("consecutive_relief_cycles"), 0))
        decision = _compute_mode_decision(
            working_summary,
            current_mode=current_mode,
            consecutive_relief_cycles=consecutive_relief_cycles,
        )

        # Update hysteresis counter first.
        direction = str(decision.get("direction") or "steady")
        if direction == "down":
            consecutive_relief_cycles += 1
            consecutive_pressure_cycles = 0
        elif direction == "up":
            consecutive_relief_cycles = 0
            consecutive_pressure_cycles += 1
        else:
            target_mode_for_cycle = str(decision.get("target_mode") or current_mode)
            if MODE_RANK.get(target_mode_for_cycle, 0) <= MODE_RANK.get(current_mode, 0):
                consecutive_pressure_cycles = 0

        mode_action = {
            "changed": False,
            "from_mode": current_mode,
            "to_mode": current_mode,
            "reason": "Mode dipertahankan",
            "at": now_iso,
        }

        auto_mode_enabled = bool(controls.get("auto_mode_enabled", True))
        mode_changed = False

        if auto_mode_enabled:
            target_mode = str(decision.get("target_mode") or current_mode)
            current_rank = MODE_RANK.get(current_mode, 0)
            target_rank = MODE_RANK.get(target_mode, 0)

            since_change = _seconds_since(runtime.get("last_mode_change_at"))
            cooldown_over = since_change is None or since_change >= float(mode_cooldown_seconds)
            confidence = _safe_float(decision.get("confidence"), 0.0)
            score = _safe_float(decision.get("score"), 0.0)

            should_change = False
            if target_rank > current_rank:
                required_cycles = (
                    upgrade_min_cycles_extreme if target_mode == "extreme" else upgrade_min_cycles_high
                )
                if target_mode == "extreme" and score >= 92.0 and confidence >= 0.70:
                    should_change = cooldown_over
                else:
                    min_confidence = 0.72 if target_mode == "extreme" else 0.68
                    should_change = (
                        cooldown_over
                        and consecutive_pressure_cycles >= required_cycles
                        and confidence >= min_confidence
                    )
            elif target_rank < current_rank:
                should_change = _should_allow_downgrade(
                    current_mode=current_mode,
                    target_mode=target_mode,
                    decision=decision,
                    consecutive_relief_cycles=consecutive_relief_cycles,
                    cooldown_over=cooldown_over,
                    confidence=confidence,
                )

            if should_change and target_mode in MODE_RANK:
                auto_reason = (
                    reason
                    or f"[AUTO] mode {target_mode.upper()} score={score:.1f} confidence={confidence:.2f}"
                )
                await set_resource_mode(
                    mode=target_mode,
                    reason=auto_reason,
                    source="auto_intelligence",
                    actor=actor,
                    ttl_minutes=mode_ttl_minutes,
                )
                await set_degrade_mode(
                    enabled=(target_mode != "normal"),
                    reason=auto_reason if target_mode != "normal" else None,
                    source="auto_intelligence",
                    actor=actor,
                    ttl_minutes=mode_ttl_minutes,
                )
                invalidate_ops_summary_cache()

                mode_changed = True
                mode_action = {
                    "changed": True,
                    "from_mode": current_mode,
                    "to_mode": target_mode,
                    "reason": auto_reason,
                    "at": now_iso,
                }
                current_mode = target_mode
                consecutive_pressure_cycles = 0
                consecutive_relief_cycles = 0
            else:
                if target_rank < MODE_RANK.get(current_mode, 0) and not cooldown_over:
                    mode_action["reason"] = "Downgrade ditahan cooldown"
                elif target_rank < MODE_RANK.get(current_mode, 0) and consecutive_relief_cycles < 2:
                    mode_action["reason"] = "Downgrade ditahan hysteresis"
                elif target_rank < MODE_RANK.get(current_mode, 0):
                    mode_action["reason"] = "Menunggu konfirmasi relief tambahan sebelum downgrade"
                elif target_rank > MODE_RANK.get(current_mode, 0):
                    mode_action["reason"] = "Menunggu sinyal tekanan konsisten sebelum upgrade"
        else:
            mode_action["reason"] = "Auto mode dinonaktifkan"

        # Auto-healing block.
        auto_heal_enabled = bool(controls.get("auto_heal_enabled", True))
        healing = {
            "status": "disabled" if not auto_heal_enabled else "not_needed",
            "executed": False,
            "summary": "Auto healing dinonaktifkan" if not auto_heal_enabled else "Belum perlu healing",
            "reason": None,
            "at": now_iso,
            "cooldown_remaining_seconds": 0,
            "actions": [],
        }

        need_heal, heal_reason = _need_healing(working_summary, force_heal=force_heal)
        if auto_heal_enabled and need_heal:
            since_heal = _seconds_since((runtime.get("last_heal") or {}).get("at"))
            cooldown_remaining = 0
            if not force_heal and since_heal is not None and since_heal < float(heal_cooldown_seconds):
                cooldown_remaining = int(max(0.0, float(heal_cooldown_seconds) - since_heal))

            if cooldown_remaining > 0:
                healing.update(
                    {
                        "status": "cooldown",
                        "summary": "Menunggu cooldown sebelum healing berikutnya",
                        "reason": heal_reason,
                        "cooldown_remaining_seconds": cooldown_remaining,
                    }
                )
            else:
                command, command_source = _resolve_heal_command()
                if not command:
                    healing.update(
                        {
                            "status": "skipped",
                            "summary": "Command auto healing belum dikonfigurasi",
                            "reason": "heal_command_missing",
                        }
                    )
                else:
                    try:
                        heal_exec = await _run_heal_command(command, timeout_seconds=heal_timeout_seconds)
                        success = int(heal_exec.get("returncode", 1)) == 0
                        action = {
                            "type": "run_command",
                            "command": " ".join(command),
                            "command_source": command_source,
                            "returncode": heal_exec.get("returncode"),
                            "stdout_tail": heal_exec.get("stdout_tail", []),
                            "stderr_tail": heal_exec.get("stderr_tail", []),
                        }
                        healing.update(
                            {
                                "status": "success" if success else "failed",
                                "executed": True,
                                "summary": (
                                    "Auto healing berhasil dieksekusi"
                                    if success
                                    else "Auto healing dijalankan tetapi command gagal"
                                ),
                                "reason": heal_reason,
                                "actions": [action],
                            }
                        )
                    except Exception as exc:
                        healing.update(
                            {
                                "status": "error",
                                "executed": True,
                                "summary": f"Auto healing error: {exc}",
                                "reason": heal_reason,
                                "actions": [
                                    {
                                        "type": "run_command",
                                        "command": " ".join(command),
                                        "command_source": command_source,
                                        "error": str(exc),
                                    }
                                ],
                            }
                        )

        runtime["current_mode"] = current_mode
        runtime["consecutive_pressure_cycles"] = consecutive_pressure_cycles
        runtime["consecutive_relief_cycles"] = consecutive_relief_cycles
        runtime["last_tick_at"] = now_iso
        runtime["last_tick_source"] = source
        runtime["last_mode_decision"] = decision
        runtime["last_mode_action"] = mode_action
        if mode_changed:
            runtime["last_mode_change_at"] = now_iso
        runtime["last_heal"] = healing

        state["runtime"] = runtime
        await _persist_state(state)

        return {
            "executed": True,
            "controls": {
                "auto_mode_enabled": auto_mode_enabled,
                "auto_heal_enabled": auto_heal_enabled,
            },
            "mode": {
                "changed": mode_changed,
                "decision": decision,
                "action": mode_action,
            },
            "healing": healing,
            "timestamp": now_iso,
        }
    finally:
        await _release_tick_lock(lock_token)


async def get_auto_intelligence_status(force_refresh: bool = False) -> Dict[str, Any]:
    state = await get_auto_intelligence_state(force_refresh=force_refresh)
    controls = state.get("controls") or {}
    runtime = state.get("runtime") or {}
    return {
        "controls": {
            "auto_mode_enabled": bool(controls.get("auto_mode_enabled", True)),
            "auto_heal_enabled": bool(controls.get("auto_heal_enabled", True)),
            "updated_at": controls.get("updated_at"),
            "source": controls.get("source"),
            "actor": controls.get("actor"),
            "reason": controls.get("reason"),
        },
        "runtime": {
            "current_mode": runtime.get("current_mode", "normal"),
            "last_tick_at": runtime.get("last_tick_at"),
            "last_tick_source": runtime.get("last_tick_source"),
            "last_mode_change_at": runtime.get("last_mode_change_at"),
            "consecutive_pressure_cycles": runtime.get("consecutive_pressure_cycles", 0),
            "consecutive_relief_cycles": runtime.get("consecutive_relief_cycles", 0),
            "last_mode_decision": runtime.get("last_mode_decision") or {},
            "last_mode_action": runtime.get("last_mode_action") or {},
            "last_heal": runtime.get("last_heal") or {},
        },
        "updated_at": state.get("updated_at"),
    }
