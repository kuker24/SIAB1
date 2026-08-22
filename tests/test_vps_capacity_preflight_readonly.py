from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "scripts" / "vps_capacity_preflight_readonly.py"
    spec = importlib.util.spec_from_file_location("vps_capacity_preflight_readonly", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _healthy_snapshot() -> dict:
    return {
        "host": {
            "memory_percent": 42.0,
            "disk_percent": 40.0,
            "inode_percent": 10.0,
            "load_per_cpu": 0.2,
            "swap_used_bytes": 0,
        },
        "containers": [
            {
                "name": "api",
                "running": True,
                "restarting": False,
                "health": "healthy",
                "restart_count": 0,
            }
        ],
        "pgbouncer": {"clients_waiting": 0},
        "database": {
            "idle_in_transaction": 0,
            "transactions_over_5s": 0,
            "advisory_locks_waiting": 0,
        },
        "redis": {
            "evicted_keys": 0,
            "rejected_connections": 0,
            "blocked_clients": 0,
            "memory_percent": 20.0,
        },
    }


def test_healthy_snapshot_passes() -> None:
    module = _load_module()
    status, findings = module.evaluate_snapshot(_healthy_snapshot())

    assert status == module.PASS
    assert all(finding.status == module.PASS for finding in findings)


def test_warning_snapshot_holds_wave() -> None:
    module = _load_module()
    snapshot = _healthy_snapshot()
    snapshot["host"]["memory_percent"] = 86.0

    status, findings = module.evaluate_snapshot(snapshot)

    assert status == module.WARNING
    assert any(f.key == "host_memory" and f.status == module.WARNING for f in findings)


def test_database_wait_or_redis_loss_signal_is_critical() -> None:
    module = _load_module()
    snapshot = _healthy_snapshot()
    snapshot["database"]["advisory_locks_waiting"] = 1
    snapshot["redis"]["evicted_keys"] = 2

    status, findings = module.evaluate_snapshot(snapshot)

    assert status == module.CRITICAL
    assert any(f.key == "db_advisory_wait" and f.status == module.CRITICAL for f in findings)
    assert any(f.key == "redis_evictions" and f.status == module.CRITICAL for f in findings)


def test_missing_evidence_is_not_treated_as_safe() -> None:
    module = _load_module()
    status, findings = module.evaluate_snapshot({})

    assert status == module.UNKNOWN
    assert any(f.status == module.UNKNOWN for f in findings)


def test_live_collector_source_has_no_mutation_commands() -> None:
    source = (ROOT / "scripts" / "vps_capacity_preflight_readonly.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden = (
        "compose down",
        "compose up",
        "docker restart",
        "docker system prune",
        "flushall",
        "flushdb",
        "delete from",
        "update exam_",
        "insert into",
        "drop table",
        "truncate table",
        "pg_terminate_backend",
    )

    for marker in forbidden:
        assert marker not in source
    assert "pg_stat_activity" in source
    assert "show pools" in source
    assert "redis-cli" in source
