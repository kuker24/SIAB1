#!/usr/bin/env bash
set -euo pipefail

API_CONTAINER="${API_CONTAINER:-}"

if [[ -z "${API_CONTAINER}" ]]; then
  API_CONTAINER="$(docker ps --filter label=com.docker.compose.service=api --format '{{.Names}}' | head -n 1 || true)"
fi

if [[ -z "${API_CONTAINER}" ]]; then
  API_CONTAINER="$(docker ps --filter name=api --format '{{.Names}}' | head -n 1 || true)"
fi

if [[ -z "${API_CONTAINER}" ]]; then
  echo "ERROR: API container tidak ditemukan. Set env API_CONTAINER terlebih dahulu." >&2
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' >&2
  exit 1
fi

echo "Using API container: ${API_CONTAINER}"

docker exec -i "${API_CONTAINER}" python - <<'PY'
import asyncio
import json
import sys

from app.core.auto_restart import get_auto_restart_schedule, get_auto_restart_status
from app.core.degrade_mode import get_degrade_mode_state
from app.core.ops_summary import get_ops_summary
from app.database import async_session_read


PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


async def main() -> int:
    async with async_session_read() as db:
        ops = await get_ops_summary(host_header="siab1.local", db=db)
    auto_restart_schedule = await get_auto_restart_schedule(force_refresh=True)
    auto_restart_status = await get_auto_restart_status(force_refresh=True)
    degrade_state = await get_degrade_mode_state(force_refresh=True)

    results = []
    failed = 0
    ops_status = str(ops.get("status") or "unknown")
    if ops_status == "critical":
        results.append((FAIL, "ops_status", f"Ops summary {ops_status}"))
        failed += 1
    elif ops_status == "warning":
        results.append((WARN, "ops_status", f"Ops summary {ops_status}"))
    else:
        results.append((PASS, "ops_status", f"Ops summary {ops_status}"))

    redis_score = float(((ops.get("key_metrics") or {}).get("redis_stability_score_percent") or 0.0))
    if redis_score >= 99.5:
        results.append((PASS, "redis_stability", f"Redis stability {redis_score:.2f}%"))
    elif redis_score >= 95.0:
        results.append((WARN, "redis_stability", f"Redis stability {redis_score:.2f}%"))
    else:
        results.append((FAIL, "redis_stability", f"Redis stability {redis_score:.2f}%"))
        failed += 1

    if bool(auto_restart_schedule.get("enabled", False)):
        results.append((PASS, "auto_restart_schedule", f"enabled @ {auto_restart_schedule.get('time_wib', '00:30')} WIB"))
    else:
        results.append((FAIL, "auto_restart_schedule", "disabled"))
        failed += 1

    restart_state = str(auto_restart_status.get("state") or "unknown").lower()
    if restart_state in {"scheduled", "success", "idle"}:
        results.append((PASS, "auto_restart_state", restart_state))
    elif restart_state in {"running", "blocked", "due"}:
        results.append((WARN, "auto_restart_state", restart_state))
    elif restart_state == "failed":
        results.append((FAIL, "auto_restart_state", restart_state))
        failed += 1
    else:
        results.append((WARN, "auto_restart_state", restart_state))

    if bool(degrade_state.get("enabled", False)):
        results.append((WARN, "degrade_mode", "ON"))
    else:
        results.append((PASS, "degrade_mode", "OFF"))

    print("=== Stable Release Readiness (VPS) ===")
    for status, key, detail in results:
        print(f"[{status}] {key}: {detail}")
    print("---")
    print(json.dumps(
        {
            "ops_status": ops_status,
            "redis_stability_score_percent": redis_score,
            "auto_restart_enabled": bool(auto_restart_schedule.get("enabled", False)),
            "auto_restart_time_wib": auto_restart_schedule.get("time_wib"),
            "auto_restart_state": auto_restart_status.get("state"),
            "degrade_mode_enabled": bool(degrade_state.get("enabled", False)),
        },
        indent=2,
    ))
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
PY
