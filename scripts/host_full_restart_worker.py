#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


STATELESS_SERVICES = [
    "api",
    "api2",
    "api3",
    "api4",
    "api5",
    "api6",
    "api7",
    "api8",
    "api_admin",
    "api_admin2",
    "celery_worker",
    "celery_beat",
    "nginx",
]
DATA_SERVICES = ["pgbouncer", "redis", "db"]
ALLOWED_SERVICES = set(STATELESS_SERVICES + DATA_SERVICES)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _control_dir() -> Path:
    return Path(
        os.environ.get("SYSTEM_FULL_RESTART_HOST_CONTROL_DIR", "/root/ujian_online/runtime_control")
    )


def _request_file() -> Path:
    return _control_dir() / "system_full_restart.request.json"


def _status_file() -> Path:
    return _control_dir() / "system_full_restart.status.json"


def _lock_file() -> Path:
    return _control_dir() / "system_full_restart.lock"


def _compose_file() -> Path:
    return Path(
        os.environ.get(
            "SYSTEM_FULL_RESTART_HOST_COMPOSE_FILE",
            "/root/ujian_online/docker-compose.production.yml",
        )
    )


def _self_restart_delay_seconds() -> float:
    return max(1.0, float(os.environ.get("SYSTEM_FULL_RESTART_SELF_DELAY_SECONDS", "2.0")))


def _request_ttl_seconds() -> int:
    return max(60, int(os.environ.get("SYSTEM_FULL_RESTART_REQUEST_TTL_SECONDS", "900")))


def _write_status(payload: dict[str, Any]) -> None:
    target = _status_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(f"{target.suffix}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)


def _read_request() -> dict[str, Any] | None:
    source = _request_file()
    if not source.exists():
        return None

    working = source.with_suffix(f"{source.suffix}.working")
    source.replace(working)
    try:
        payload = json.loads(working.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
        return None
    finally:
        working.unlink(missing_ok=True)


def _resolve_requesting_service(container_id: str) -> str:
    if not container_id:
        return ""
    command = [
        "docker",
        "inspect",
        "--format",
        "{{ index .Config.Labels \"com.docker.compose.service\" }}",
        container_id,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=20)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _build_services(payload: dict[str, Any]) -> list[str]:
    raw_services = payload.get("services_requested")
    if isinstance(raw_services, list):
        requested = [str(item).strip() for item in raw_services if str(item).strip() in ALLOWED_SERVICES]
    else:
        requested = list(STATELESS_SERVICES)
        if bool(payload.get("include_data_services", True)):
            requested.extend(DATA_SERVICES)

    seen: set[str] = set()
    ordered: list[str] = []
    for service in requested:
        if service in seen or service not in ALLOWED_SERVICES:
            continue
        seen.add(service)
        ordered.append(service)
    return ordered


def _validate_request(payload: dict[str, Any]) -> tuple[str, list[str]]:
    request_id = str(payload.get("request_id") or "").strip()
    if not request_id:
        raise RuntimeError("request_id kosong")

    created_raw = str(payload.get("created_at") or "").strip()
    if created_raw:
        created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)
        if age > timedelta(seconds=_request_ttl_seconds()):
            raise RuntimeError(f"request terlalu lama ({int(age.total_seconds())}s)")

    services = _build_services(payload)
    if not services:
        raise RuntimeError("tidak ada service valid untuk di-restart")

    return request_id, services


def _run_compose_restart(service: str, timeout_seconds: int) -> None:
    compose_file = _compose_file()
    command = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "restart",
        service,
    ]
    result = subprocess.run(
        command,
        cwd=str(compose_file.parent),
        capture_output=True,
        text=True,
        check=False,
        timeout=max(60, timeout_seconds),
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        raise RuntimeError(f"restart {service} gagal: {detail}")


def main() -> int:
    control_dir = _control_dir()
    control_dir.mkdir(parents=True, exist_ok=True)

    with _lock_file().open("a+", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0

        payload = _read_request()
        if not payload:
            return 0

        request_id = str(payload.get("request_id") or "").strip() or "unknown"
        timeout_seconds = max(60, min(int(payload.get("timeout_seconds") or 300), 1200))

        try:
            request_id, services = _validate_request(payload)
            requesting_service = _resolve_requesting_service(
                str(payload.get("requesting_container_id") or "").strip()
            )
            non_self_services = [service for service in services if service != requesting_service]
            self_services = [service for service in services if service == requesting_service]
            ordered_services = non_self_services + self_services

            _write_status(
                {
                    "request_id": request_id,
                    "state": "running",
                    "message": "Host worker sedang menjalankan full restart antar sesi.",
                    "services_requested": services,
                    "services_restarted": [],
                    "requesting_service": requesting_service,
                    "updated_at": _now_iso(),
                }
            )

            restarted: list[str] = []
            for index, service in enumerate(ordered_services):
                is_self_last = bool(self_services) and index == len(ordered_services) - 1 and service in self_services
                if is_self_last:
                    _write_status(
                        {
                            "request_id": request_id,
                            "state": "success",
                            "message": "Full restart hampir selesai. Service API pemanggil dijadwalkan restart terakhir.",
                            "services_requested": services,
                            "services_restarted": restarted,
                            "requesting_service": requesting_service,
                            "self_restart_scheduled": True,
                            "updated_at": _now_iso(),
                        }
                    )
                    time.sleep(_self_restart_delay_seconds())

                if bool(payload.get("dry_run", False)):
                    restarted.append(service)
                    continue

                _run_compose_restart(service, timeout_seconds=timeout_seconds)
                restarted.append(service)

            _write_status(
                {
                    "request_id": request_id,
                    "state": "success",
                    "message": "Host worker menyelesaikan full restart antar sesi.",
                    "services_requested": services,
                    "services_restarted": restarted,
                    "requesting_service": requesting_service,
                    "self_restart_scheduled": bool(self_services),
                    "updated_at": _now_iso(),
                }
            )
            return 0
        except Exception as exc:
            _write_status(
                {
                    "request_id": request_id,
                    "state": "failed",
                    "message": str(exc),
                    "updated_at": _now_iso(),
                }
            )
            print(f"[host_full_restart_worker] ERROR: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
