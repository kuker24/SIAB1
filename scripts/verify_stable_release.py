#!/usr/bin/env python3
"""
Stable release readiness checker.

Focus:
- Core runtime summary must be non-critical.
- Redis stability score should remain high in normal mode.
- Auto restart scheduler (WIB) harus aktif.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import List, Tuple

from app.core.auto_restart import get_auto_restart_schedule, get_auto_restart_status
from app.core.degrade_mode import get_degrade_mode_state
from app.core.ops_summary import get_ops_summary
from app.database import async_session_read


PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


async def _collect() -> dict:
    async with async_session_read() as db:
        ops = await get_ops_summary(host_header="siab1.local", db=db)
    return {
        "ops": ops,
        "auto_restart_schedule": await get_auto_restart_schedule(force_refresh=True),
        "auto_restart_status": await get_auto_restart_status(force_refresh=True),
        "degrade_state": await get_degrade_mode_state(force_refresh=True),
    }


def _check(payload: dict) -> Tuple[List[Tuple[str, str, str]], int]:
    results: List[Tuple[str, str, str]] = []
    failed = 0

    ops = payload.get("ops") or {}
    policy = ops.get("policy") or {}
    auto_restart_schedule = payload.get("auto_restart_schedule") or {}
    auto_restart_status = payload.get("auto_restart_status") or {}
    key_metrics = ops.get("key_metrics") or {}

    ops_status = str(ops.get("status") or "unknown")
    if ops_status == "critical":
        results.append((FAIL, "ops_status", f"Ops summary critical ({ops_status})"))
        failed += 1
    elif ops_status == "warning":
        results.append((WARN, "ops_status", f"Ops summary warning ({ops_status})"))
    else:
        results.append((PASS, "ops_status", f"Ops summary {ops_status}"))

    redis_score = float(key_metrics.get("redis_stability_score_percent") or 0.0)
    if redis_score >= 99.5:
        results.append((PASS, "redis_stability", f"Redis stability {redis_score:.2f}%"))
    elif redis_score >= 95.0:
        results.append((WARN, "redis_stability", f"Redis stability {redis_score:.2f}% (<99.5%)"))
    else:
        results.append((FAIL, "redis_stability", f"Redis stability {redis_score:.2f}% (<95%)"))
        failed += 1

    if bool(auto_restart_schedule.get("enabled", False)):
        results.append(
            (
                PASS,
                "auto_restart_schedule",
                f"Auto restart active @ {auto_restart_schedule.get('time_wib', '00:30')} WIB",
            )
        )
    else:
        results.append((FAIL, "auto_restart_schedule", "Auto restart scheduler disabled"))
        failed += 1

    restart_state = str(auto_restart_status.get("state") or "unknown").lower()
    if restart_state in {"scheduled", "success", "idle"}:
        results.append((PASS, "auto_restart_state", f"Auto restart state {restart_state}"))
    elif restart_state in {"running", "blocked", "due"}:
        results.append((WARN, "auto_restart_state", f"Auto restart state {restart_state}"))
    elif restart_state == "failed":
        results.append((FAIL, "auto_restart_state", f"Auto restart state {restart_state}"))
        failed += 1
    else:
        results.append((WARN, "auto_restart_state", f"Auto restart state {restart_state}"))

    if policy.get("degrade_mode"):
        results.append((WARN, "degrade_mode", "Degrade mode currently ON"))
    else:
        results.append((PASS, "degrade_mode", "Degrade mode OFF (normal)"))

    return results, failed


async def main() -> int:
    payload = await _collect()
    results, failed = _check(payload)

    print("=== Stable Release Readiness ===")
    for status, key, detail in results:
        print(f"[{status}] {key}: {detail}")

    print("---")
    print(json.dumps(
        {
            "ops_status": (payload.get("ops") or {}).get("status"),
            "redis_stability_score_percent": ((payload.get("ops") or {}).get("key_metrics") or {}).get(
                "redis_stability_score_percent"
            ),
            "auto_restart_enabled": (payload.get("auto_restart_schedule") or {}).get("enabled"),
            "auto_restart_time_wib": (payload.get("auto_restart_schedule") or {}).get("time_wib"),
            "auto_restart_state": (payload.get("auto_restart_status") or {}).get("state"),
            "degrade_mode_enabled": (payload.get("degrade_state") or {}).get("enabled"),
        },
        indent=2,
    ))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
