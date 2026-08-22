#!/usr/bin/env python3
"""Read-only capacity preflight for SIAB1 exam waves.

The default mode evaluates a sanitized JSON fixture. Live collection requires
``--collect-live`` and runs only bounded status/SELECT/INFO commands. It never
restarts services, changes configuration, or writes application data.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PASS = "PASS"
WARNING = "WARNING"
CRITICAL = "CRITICAL"
UNKNOWN = "UNKNOWN"
_STATUS_RANK = {PASS: 0, WARNING: 1, UNKNOWN: 2, CRITICAL: 3}


@dataclass(frozen=True)
class Finding:
    status: str
    key: str
    detail: str


def _worst_status(findings: Iterable[Finding]) -> str:
    return max((finding.status for finding in findings), key=_STATUS_RANK.get, default=UNKNOWN)


def _number(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _threshold(
    findings: list[Finding],
    *,
    key: str,
    value: float | None,
    warning: float,
    critical: float,
    unit: str = "%",
) -> None:
    if value is None:
        findings.append(Finding(UNKNOWN, key, "metric unavailable"))
    elif value >= critical:
        findings.append(Finding(CRITICAL, key, f"{value:.1f}{unit} >= {critical:.1f}{unit}"))
    elif value >= warning:
        findings.append(Finding(WARNING, key, f"{value:.1f}{unit} >= {warning:.1f}{unit}"))
    else:
        findings.append(Finding(PASS, key, f"{value:.1f}{unit}"))


def evaluate_snapshot(snapshot: dict[str, Any]) -> tuple[str, list[Finding]]:
    findings: list[Finding] = []
    host = snapshot.get("host") or {}
    database = snapshot.get("database") or {}
    pgbouncer = snapshot.get("pgbouncer") or {}
    redis = snapshot.get("redis") or {}
    containers = snapshot.get("containers")

    _threshold(
        findings,
        key="host_memory",
        value=_number(host, "memory_percent"),
        warning=85.0,
        critical=92.0,
    )
    _threshold(
        findings,
        key="root_disk",
        value=_number(host, "disk_percent"),
        warning=90.0,
        critical=95.0,
    )
    _threshold(
        findings,
        key="root_inodes",
        value=_number(host, "inode_percent"),
        warning=90.0,
        critical=95.0,
    )
    _threshold(
        findings,
        key="load_per_cpu",
        value=_number(host, "load_per_cpu"),
        warning=0.85,
        critical=1.5,
        unit="",
    )

    swap_used = _number(host, "swap_used_bytes")
    if swap_used is None:
        findings.append(Finding(UNKNOWN, "swap", "metric unavailable"))
    elif swap_used >= 256 * 1024 * 1024:
        findings.append(Finding(CRITICAL, "swap", f"{swap_used / 1024 / 1024:.0f} MiB used"))
    elif swap_used > 0:
        findings.append(Finding(WARNING, "swap", f"{swap_used / 1024 / 1024:.1f} MiB used"))
    else:
        findings.append(Finding(PASS, "swap", "unused"))

    if not isinstance(containers, list) or not containers:
        findings.append(Finding(UNKNOWN, "containers", "container state unavailable"))
    else:
        unhealthy = [str(item.get("name") or "unknown") for item in containers if item.get("health") == "unhealthy"]
        stopped = [str(item.get("name") or "unknown") for item in containers if item.get("running") is False]
        restarting = [str(item.get("name") or "unknown") for item in containers if item.get("restarting") is True]
        restart_count = sum(int(item.get("restart_count") or 0) for item in containers)
        if unhealthy or stopped or restarting:
            detail = ", ".join(unhealthy + stopped + restarting)
            findings.append(Finding(CRITICAL, "containers", f"not stable: {detail}"))
        elif restart_count > 0:
            findings.append(Finding(WARNING, "containers", f"restart count={restart_count}"))
        else:
            findings.append(Finding(PASS, "containers", f"{len(containers)} stable"))

    pool_waiting = _number(pgbouncer, "clients_waiting")
    if pool_waiting is None:
        findings.append(Finding(UNKNOWN, "pgbouncer_wait", "metric unavailable"))
    elif pool_waiting >= 10:
        findings.append(Finding(CRITICAL, "pgbouncer_wait", f"{pool_waiting:.0f} clients waiting"))
    elif pool_waiting > 0:
        findings.append(Finding(WARNING, "pgbouncer_wait", f"{pool_waiting:.0f} clients waiting"))
    else:
        findings.append(Finding(PASS, "pgbouncer_wait", "no waiting clients"))

    idle_tx = _number(database, "idle_in_transaction")
    if idle_tx is None:
        findings.append(Finding(UNKNOWN, "db_idle_transaction", "metric unavailable"))
    elif idle_tx >= 5:
        findings.append(Finding(CRITICAL, "db_idle_transaction", f"{idle_tx:.0f} sessions"))
    elif idle_tx > 0:
        findings.append(Finding(WARNING, "db_idle_transaction", f"{idle_tx:.0f} sessions"))
    else:
        findings.append(Finding(PASS, "db_idle_transaction", "zero"))

    advisory_waiting = _number(database, "advisory_locks_waiting")
    if advisory_waiting is None:
        findings.append(Finding(UNKNOWN, "db_advisory_wait", "metric unavailable"))
    elif advisory_waiting > 0:
        findings.append(Finding(CRITICAL, "db_advisory_wait", f"{advisory_waiting:.0f} waiting locks"))
    else:
        findings.append(Finding(PASS, "db_advisory_wait", "zero"))

    long_transactions = _number(database, "transactions_over_5s")
    if long_transactions is None:
        findings.append(Finding(UNKNOWN, "db_long_transactions", "metric unavailable"))
    elif long_transactions >= 5:
        findings.append(Finding(CRITICAL, "db_long_transactions", f"{long_transactions:.0f} transactions"))
    elif long_transactions > 0:
        findings.append(Finding(WARNING, "db_long_transactions", f"{long_transactions:.0f} transactions"))
    else:
        findings.append(Finding(PASS, "db_long_transactions", "zero"))

    for key, label in (("evicted_keys", "redis_evictions"), ("rejected_connections", "redis_rejections")):
        value = _number(redis, key)
        if value is None:
            findings.append(Finding(UNKNOWN, label, "metric unavailable"))
        elif value > 0:
            findings.append(Finding(CRITICAL, label, f"{value:.0f}"))
        else:
            findings.append(Finding(PASS, label, "zero"))

    blocked_clients = _number(redis, "blocked_clients")
    if blocked_clients is None:
        findings.append(Finding(UNKNOWN, "redis_blocked_clients", "metric unavailable"))
    elif blocked_clients >= 10:
        findings.append(Finding(CRITICAL, "redis_blocked_clients", f"{blocked_clients:.0f}"))
    elif blocked_clients > 0:
        findings.append(Finding(WARNING, "redis_blocked_clients", f"{blocked_clients:.0f}"))
    else:
        findings.append(Finding(PASS, "redis_blocked_clients", "zero"))

    _threshold(
        findings,
        key="redis_memory",
        value=_number(redis, "memory_percent"),
        warning=85.0,
        critical=95.0,
    )

    return _worst_status(findings), findings


def _run(command: list[str], timeout: int = 20) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "command failed")
    return result.stdout


def _compose_prefix(compose_file: str) -> list[str]:
    if shutil.which("docker-compose"):
        return ["docker-compose", "-f", compose_file]
    return ["docker", "compose", "-f", compose_file]


def _meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, raw = line.split(":", 1)
        amount = int(raw.strip().split()[0]) * 1024
        values[key] = amount
    return values


def _parse_redis_info(raw: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def collect_live(compose_file: str) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    snapshot: dict[str, Any] = {}

    mem = _meminfo()
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", 0)
    swap_total = mem.get("SwapTotal", 0)
    swap_free = mem.get("SwapFree", 0)
    disk = shutil.disk_usage("/")
    stat = os.statvfs("/")
    inode_total = stat.f_files
    inode_free = stat.f_ffree
    cpu_count = os.cpu_count() or 1
    snapshot["host"] = {
        "memory_percent": ((total - available) / total * 100.0) if total else None,
        "swap_used_bytes": max(0, swap_total - swap_free),
        "disk_percent": (disk.used / disk.total * 100.0) if disk.total else None,
        "inode_percent": ((inode_total - inode_free) / inode_total * 100.0) if inode_total else None,
        "load_per_cpu": os.getloadavg()[0] / cpu_count,
    }

    compose = _compose_prefix(compose_file)
    containers: list[dict[str, Any]] = []
    try:
        ids = [value for value in _run(compose + ["ps", "-q"]).splitlines() if value]
        if ids:
            raw = _run(["docker", "inspect", *ids], timeout=30)
            for item in json.loads(raw):
                state = item.get("State") or {}
                containers.append(
                    {
                        "name": str(item.get("Name") or "").lstrip("/"),
                        "running": bool(state.get("Running")),
                        "restarting": bool(state.get("Restarting")),
                        "health": (state.get("Health") or {}).get("Status"),
                        "restart_count": int(item.get("RestartCount") or 0),
                    }
                )
    except Exception as exc:
        errors.append(f"containers: {exc}")
    snapshot["containers"] = containers

    try:
        pool_csv = _run(
            compose
            + [
                "exec",
                "-T",
                "pgbouncer",
                "sh",
                "-lc",
                'PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 6432 -U "$DB_USER" -d pgbouncer --csv -c "SHOW POOLS;"',
            ]
        )
        rows = list(csv.DictReader(io.StringIO(pool_csv)))
        snapshot["pgbouncer"] = {
            "clients_waiting": sum(int(row.get("cl_waiting") or 0) for row in rows)
        }
    except Exception as exc:
        errors.append(f"pgbouncer: {exc}")
        snapshot["pgbouncer"] = {}

    try:
        db_raw = _run(
            compose
            + [
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "examuser",
                "-d",
                "exam_system",
                "-X",
                "-At",
                "-F",
                "|",
                "-c",
                "SELECT COUNT(*) FILTER (WHERE state = 'idle in transaction'), "
                "COUNT(*) FILTER (WHERE xact_start IS NOT NULL AND clock_timestamp() - xact_start > interval '5 seconds'), "
                "(SELECT COUNT(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted) "
                "FROM pg_stat_activity WHERE datname = current_database();",
            ]
        ).strip()
        idle_tx, long_tx, advisory_wait = (int(value) for value in db_raw.split("|"))
        snapshot["database"] = {
            "idle_in_transaction": idle_tx,
            "transactions_over_5s": long_tx,
            "advisory_locks_waiting": advisory_wait,
        }
    except Exception as exc:
        errors.append(f"database: {exc}")
        snapshot["database"] = {}

    try:
        redis_raw = _run(
            compose + ["exec", "-T", "redis", "redis-cli", "INFO", "all"]
        )
        info = _parse_redis_info(redis_raw)
        used_memory = int(info.get("used_memory") or 0)
        maxmemory = int(info.get("maxmemory") or 0)
        snapshot["redis"] = {
            "evicted_keys": int(info.get("evicted_keys") or 0),
            "rejected_connections": int(info.get("rejected_connections") or 0),
            "blocked_clients": int(info.get("blocked_clients") or 0),
            "memory_percent": (used_memory / maxmemory * 100.0) if maxmemory else None,
        }
    except Exception as exc:
        errors.append(f"redis: {exc}")
        snapshot["redis"] = {}

    return snapshot, errors


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input-json", type=Path, help="Evaluate a sanitized JSON snapshot.")
    source.add_argument(
        "--collect-live",
        action="store_true",
        help="Collect bounded read-only metrics from the current VPS.",
    )
    parser.add_argument("--compose-file", default="docker-compose.production.yml")
    parser.add_argument("--output-json", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    errors: list[str] = []
    if args.collect_live:
        snapshot, errors = collect_live(args.compose_file)
    else:
        snapshot = json.loads(args.input_json.read_text(encoding="utf-8"))

    status, findings = evaluate_snapshot(snapshot)
    if errors:
        status = _worst_status([*findings, Finding(UNKNOWN, "collection", "; ".join(errors))])
        findings.append(Finding(UNKNOWN, "collection", "; ".join(errors)))

    result = {
        "status": status,
        "findings": [finding.__dict__ for finding in findings],
        "snapshot": snapshot,
        "collection_errors": errors,
    }
    if args.output_json:
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(f"=== SIAB1 Capacity Preflight: {status} ===")
    for finding in findings:
        print(f"[{finding.status}] {finding.key}: {finding.detail}")

    if status == PASS:
        print("Decision: capacity indicators are clear for the next controlled wave.")
        return 0
    if status == WARNING:
        print("Decision: hold the next wave and review warnings.")
        return 1
    print("Decision: do not start the next wave; evidence is critical or incomplete.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
