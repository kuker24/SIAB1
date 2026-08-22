"""Restart backend helpers for monitoring API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException

from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)

DOCKER_SOCKET_PATH = "/var/run/docker.sock"
FULL_RESTART_REQUEST_FILE_ENV = "SYSTEM_FULL_RESTART_REQUEST_FILE"
FULL_RESTART_STATUS_FILE_ENV = "SYSTEM_FULL_RESTART_STATUS_FILE"


async def _delete_redis_keys_by_patterns(patterns: List[str]) -> int:
    deleted_total = 0
    redis = await get_redis()
    for pattern in patterns:
        batch: List[str] = []
        async for key in redis.scan_iter(match=pattern, count=512):
            batch.append(str(key))
            if len(batch) >= 512:
                deleted_total += int(await redis.delete(*batch))
                batch.clear()
        if batch:
            deleted_total += int(await redis.delete(*batch))
    return deleted_total


def _docker_socket_control_enabled() -> bool:
    return os.getenv("MONITORING_ALLOW_DOCKER_SOCKET", "false").strip().lower() == "true"


def _get_signal_restart_paths() -> Dict[str, str]:
    return {
        "request_file": str(os.getenv(FULL_RESTART_REQUEST_FILE_ENV, "") or "").strip(),
        "status_file": str(os.getenv(FULL_RESTART_STATUS_FILE_ENV, "") or "").strip(),
    }


def _signal_restart_control_status() -> Dict[str, Any]:
    paths = _get_signal_restart_paths()
    request_file = paths["request_file"]
    status_file = paths["status_file"]
    request_dir = os.path.dirname(request_file) or "."
    status_dir = os.path.dirname(status_file) or "."
    configured = bool(request_file and status_file)
    request_dir_ready = configured and os.path.isdir(request_dir) and os.access(request_dir, os.W_OK)
    status_dir_ready = configured and os.path.isdir(status_dir) and os.access(status_dir, os.R_OK | os.W_OK)
    return {
        "configured": configured,
        "available": bool(configured and request_dir_ready and status_dir_ready),
        "request_dir_ready": bool(request_dir_ready),
        "status_dir_ready": bool(status_dir_ready),
        "request_file": request_file,
        "status_file": status_file,
    }


def _restart_backend_status() -> Dict[str, Any]:
    custom_command = str(os.getenv("SYSTEM_FULL_RESTART_COMMAND", "") or "").strip()
    socket_enabled = _docker_socket_control_enabled()
    socket_available = socket_enabled and os.path.exists(DOCKER_SOCKET_PATH)
    signal_status = _signal_restart_control_status()
    return {
        "signal_control_configured": signal_status["configured"],
        "signal_control_available": signal_status["available"],
        "docker_socket_enabled": socket_enabled,
        "docker_socket_available": socket_available,
        "custom_command_configured": bool(custom_command),
        "full_restart_available": signal_status["available"] or bool(custom_command) or socket_available,
        "hint": (
            "Set SYSTEM_FULL_RESTART_REQUEST_FILE + SYSTEM_FULL_RESTART_STATUS_FILE untuk restart host terkontrol, "
            "atau SYSTEM_FULL_RESTART_COMMAND untuk restart terkontrol dari container, "
            "atau aktifkan MONITORING_ALLOW_DOCKER_SOCKET=true jika Anda menerima risikonya."
        ),
    }


def _ensure_full_restart_available() -> None:
    status_info = _restart_backend_status()
    if not status_info["full_restart_available"]:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "FULL_RESTART_UNAVAILABLE",
                "message": "Backend full restart tidak dikonfigurasi pada API ini.",
                "restart_backend": status_info,
            },
        )


async def _docker_api_request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 20,
) -> httpx.Response:
    transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET_PATH)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://docker",
        timeout=timeout_seconds,
    ) as client:
        return await client.request(method=method, url=path, params=params)


async def _detect_compose_project_from_runtime() -> str:
    explicit = str(os.getenv("SYSTEM_RESTART_COMPOSE_PROJECT", "") or "").strip()
    if explicit:
        return explicit

    current_container_id = str(os.getenv("HOSTNAME", "") or "").strip()
    if current_container_id:
        try:
            inspect_resp = await _docker_api_request(
                "GET",
                f"/containers/{current_container_id}/json",
                timeout_seconds=15,
            )
            if inspect_resp.status_code == 200:
                payload = inspect_resp.json()
                labels = (((payload or {}).get("Config") or {}).get("Labels") or {})
                project = str(labels.get("com.docker.compose.project") or "").strip()
                if project:
                    return project
        except Exception:
            pass

    fallback = str(os.getenv("COMPOSE_PROJECT_NAME", "") or "").strip()
    if fallback:
        return fallback
    return "siab1"


async def _list_service_containers_from_socket(
    *,
    compose_project: str,
    service_name: str,
) -> List[Dict[str, Any]]:
    filters = {
        "label": [
            f"com.docker.compose.project={compose_project}",
            f"com.docker.compose.service={service_name}",
        ],
        "status": ["running"],
    }
    resp = await _docker_api_request(
        "GET",
        "/containers/json",
        params={"all": 0, "filters": json.dumps(filters, separators=(",", ":"))},
        timeout_seconds=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"docker API list container gagal untuk service={service_name} (status={resp.status_code})"
        )
    payload = resp.json()
    if isinstance(payload, list):
        return payload
    return []


async def _restart_container_from_socket(container_id: str, timeout_seconds: int = 30) -> None:
    resp = await _docker_api_request(
        "POST",
        f"/containers/{container_id}/restart",
        params={"t": max(10, min(int(timeout_seconds or 30), 120))},
        timeout_seconds=max(30, timeout_seconds),
    )
    # 204 = restarted, 304 = already stopped
    if resp.status_code not in {204, 304}:
        body = (resp.text or "").strip()
        raise RuntimeError(
            f"docker API restart gagal untuk container={container_id} status={resp.status_code} body={body[:300]}"
        )


async def _execute_full_restart_via_socket(
    *,
    include_data_services: bool,
    timeout_seconds: int,
) -> Dict[str, Any]:
    if not _docker_socket_control_enabled():
        raise RuntimeError("Docker socket restart dinonaktifkan oleh konfigurasi keamanan")
    if not os.path.exists(DOCKER_SOCKET_PATH):
        raise RuntimeError("Docker socket tidak tersedia di container API")

    compose_project = await _detect_compose_project_from_runtime()
    services_requested = _build_full_restart_services(include_data_services)
    current_container_id = str(os.getenv("HOSTNAME", "") or "").strip()

    service_container_map: Dict[str, List[Dict[str, Any]]] = {}
    for service_name in services_requested:
        containers = await _list_service_containers_from_socket(
            compose_project=compose_project,
            service_name=service_name,
        )
        if containers:
            service_container_map[service_name] = containers

    restart_queue: List[Dict[str, Any]] = []
    for service_name in services_requested:
        for container in service_container_map.get(service_name, []):
            restart_queue.append(
                {
                    "service": service_name,
                    "id": str(container.get("Id") or ""),
                    "name": ",".join(container.get("Names") or []),
                }
            )

    if not restart_queue:
        return {
            "mode": "docker_socket",
            "compose_project": compose_project,
            "services_requested": services_requested,
            "services_restarted": [],
            "containers_restarted": [],
            "self_restart_scheduled": False,
        }

    queue_without_self: List[Dict[str, Any]] = []
    self_item: Optional[Dict[str, Any]] = None
    for item in restart_queue:
        container_id = item.get("id", "")
        if current_container_id and container_id.startswith(current_container_id):
            self_item = item
            continue
        queue_without_self.append(item)

    restarted_containers: List[Dict[str, str]] = []
    for item in queue_without_self:
        await _restart_container_from_socket(item["id"], timeout_seconds=timeout_seconds)
        restarted_containers.append(
            {
                "service": item["service"],
                "container_id": item["id"][:12],
                "container_name": item.get("name", ""),
            }
        )

    self_restart_scheduled = False
    if self_item:
        self_restart_scheduled = True

        async def _restart_self_later(container_id: str) -> None:
            await asyncio.sleep(1.0)
            try:
                await _restart_container_from_socket(container_id, timeout_seconds=timeout_seconds)
            except Exception as exc:
                logger.error("Self container restart failed: %s", exc, exc_info=True)

        asyncio.create_task(_restart_self_later(self_item["id"]))
        restarted_containers.append(
            {
                "service": self_item["service"],
                "container_id": self_item["id"][:12],
                "container_name": self_item.get("name", ""),
            }
        )

    restarted_services = sorted(
        {
            item["service"]
            for item in restarted_containers
            if item.get("service")
        }
    )

    return {
        "mode": "docker_socket",
        "compose_project": compose_project,
        "services_requested": services_requested,
        "services_restarted": restarted_services,
        "containers_restarted": restarted_containers,
        "self_restart_scheduled": self_restart_scheduled,
    }


def _resolve_compose_context() -> Dict[str, str]:
    """
    Resolve docker compose file/context for full restart execution.

    Priority:
    1) SYSTEM_RESTART_COMPOSE_FILE env
    2) ${SIAB1_HOME}/docker-compose.production.yml
    3) /app/docker-compose.production.yml
    4) ./docker-compose.production.yml (current working dir)
    """
    explicit_compose = str(os.getenv("SYSTEM_RESTART_COMPOSE_FILE", "") or "").strip()
    if explicit_compose and os.path.exists(explicit_compose):
        return {
            "project_dir": os.path.dirname(explicit_compose) or ".",
            "compose_file": explicit_compose,
        }

    candidates = [
        os.path.join(os.getenv("SIAB1_HOME", "/opt/siab1"), "docker-compose.production.yml"),
        "/app/docker-compose.production.yml",
        os.path.join(os.getcwd(), "docker-compose.production.yml"),
    ]
    for compose_file in candidates:
        if os.path.exists(compose_file):
            return {
                "project_dir": os.path.dirname(compose_file) or ".",
                "compose_file": compose_file,
            }

    raise RuntimeError("docker-compose.production.yml tidak ditemukan untuk full restart")


def _build_full_restart_services(include_data_services: bool) -> List[str]:
    """
    Build restart target services.

    Stateless services are always included.
    Data services included by default for true "restart semuanya".
    """
    services = [
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
    if include_data_services:
        services.extend(["pgbouncer", "redis", "db"])
    return services


async def _run_compose_command(
    command: List[str],
    project_dir: str,
    timeout_seconds: int,
) -> subprocess.CompletedProcess:
    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

    return await asyncio.to_thread(_run)


async def _write_json_atomic(path: str, payload: Dict[str, Any]) -> None:
    def _write() -> None:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)

    await asyncio.to_thread(_write)


async def _read_json_file_if_exists(path: str) -> Optional[Dict[str, Any]]:
    def _read() -> Optional[Dict[str, Any]]:
        if not path or not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return payload
        return {"value": payload}

    try:
        return await asyncio.to_thread(_read)
    except (OSError, json.JSONDecodeError):
        return None


async def _execute_full_restart_via_signal(
    *,
    include_data_services: bool,
    timeout_seconds: int,
    actor: Optional[str],
    reason: Optional[str],
) -> Dict[str, Any]:
    signal_status = _signal_restart_control_status()
    if not signal_status["available"]:
        raise RuntimeError("Host-controlled full restart belum siap di API container")

    request_file = signal_status["request_file"]
    status_file = signal_status["status_file"]
    request_id = uuid.uuid4().hex
    services_requested = _build_full_restart_services(include_data_services)
    request_payload = {
        "request_id": request_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "actor": str(actor or "system"),
        "reason": str(reason or "Manual full restart"),
        "mode": "full",
        "dry_run": False,
        "timeout_seconds": timeout_seconds,
        "include_data_services": bool(include_data_services),
        "services_requested": services_requested,
        "requesting_container_id": str(os.getenv("HOSTNAME", "") or "").strip(),
    }
    await _write_json_atomic(request_file, request_payload)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(90.0, float(timeout_seconds + 45))
    last_state = "queued"
    last_message = "Menunggu host worker memproses full restart."

    while loop.time() < deadline:
        status_payload = await _read_json_file_if_exists(status_file)
        if isinstance(status_payload, dict) and status_payload.get("request_id") == request_id:
            last_state = str(status_payload.get("state") or "unknown").lower()
            last_message = str(status_payload.get("message") or last_message)
            if last_state == "success":
                return {
                    "mode": "host_signal",
                    "request_id": request_id,
                    "services_requested": services_requested,
                    **status_payload,
                }
            if last_state == "failed":
                raise RuntimeError(last_message or "Host worker melaporkan full restart gagal")
        await asyncio.sleep(1.0)

    raise RuntimeError(
        f"Host worker timeout saat full restart (state={last_state}): {last_message}"
    )


async def _execute_full_restart(
    *,
    include_data_services: bool,
    timeout_seconds: int,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    timeout_seconds = max(60, min(int(timeout_seconds or 300), 1200))
    services_requested = _build_full_restart_services(include_data_services)
    status_info = _restart_backend_status()

    signal_result = None
    signal_error: Optional[str] = None
    if status_info["signal_control_available"]:
        try:
            signal_result = await _execute_full_restart_via_signal(
                include_data_services=include_data_services,
                timeout_seconds=timeout_seconds,
                actor=actor,
                reason=reason,
            )
        except Exception as exc:
            signal_error = str(exc)

    socket_result = None
    socket_error: Optional[str] = None
    if status_info["docker_socket_available"]:
        try:
            socket_result = await _execute_full_restart_via_socket(
                include_data_services=include_data_services,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            socket_error = str(exc)

    if signal_result is not None:
        return {
            **signal_result,
            "signal_fallback_error": signal_error,
        }

    custom_command = str(os.getenv("SYSTEM_FULL_RESTART_COMMAND", "") or "").strip()
    if custom_command:
        ctx = _resolve_compose_context()
        project_dir = ctx["project_dir"]
        compose_file = ctx["compose_file"]
        command = shlex.split(custom_command)
        if not command:
            raise RuntimeError("SYSTEM_FULL_RESTART_COMMAND kosong")
        run_result = await _run_compose_command(
            command,
            project_dir=project_dir,
            timeout_seconds=timeout_seconds,
        )
        if run_result.returncode != 0:
            raise RuntimeError(
                f"Perintah custom full restart gagal (code={run_result.returncode}): "
                f"{(run_result.stderr or '').strip() or (run_result.stdout or '').strip()}"
            )
        return {
            "mode": "custom_command",
            "command": " ".join(command),
            "services_requested": services_requested,
            "services_restarted": services_requested,
            "stdout_tail": (run_result.stdout or "").splitlines()[-20:],
            "stderr_tail": (run_result.stderr or "").splitlines()[-20:],
            "project_dir": project_dir,
            "compose_file": compose_file,
        }

    if socket_result is not None:
        return {
            **socket_result,
            "signal_fallback_error": signal_error,
            "socket_fallback_error": socket_error,
        }

    if signal_error:
        raise RuntimeError(
            f"Full restart gagal dijalankan via host control: {signal_error}. {status_info['hint']}"
        )
    if socket_error:
        raise RuntimeError(
            f"Full restart gagal dijalankan. Socket error: {socket_error}. {status_info['hint']}"
        )
    raise RuntimeError(status_info["hint"])
