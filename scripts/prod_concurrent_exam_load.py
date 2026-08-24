#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import plistlib
import re
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin
from urllib.parse import urlparse, urlunparse

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "requests belum tersedia. Install dulu dengan: python3 -m pip install requests"
    ) from exc


USER_AGENT = "Prod-Exam-LoadTest/1.0"
DEFAULT_PHASES = [50, 200, 620]
FALLBACK_MINIMUM_APK_TOKEN = "BUILD-19700101000000-AAAAAA"
FALLBACK_APP_SIGNATURE = "A" * 64
RETRYABLE_HTTP_STATUS = {429, 502, 503, 504}
APP_SIGNATURE_RE = re.compile(r"^[a-f0-9]{64}$", re.IGNORECASE)


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: Any):
        self.method = method
        self.path = path
        self.status = status
        self.body = body
        super().__init__(f"{method} {path} -> {status}: {body}")


@dataclass(frozen=True)
class Participant:
    user_id: int
    username: str
    full_name: str


@dataclass
class LoginResult:
    participant: Participant
    ok: bool
    token: Optional[str]
    latency_ms: float
    error: Optional[str] = None


@dataclass
class ProvisionResult:
    username: str
    ok: bool
    latency_ms: float
    user_id: Optional[int] = None
    error: Optional[str] = None


@dataclass
class ExamFlowResult:
    participant: Participant
    session_id: Optional[int]
    start_ok: bool
    status_ok: bool
    remaining_ok: bool
    answer_ok: bool
    submit_ok: bool
    start_latency_ms: Optional[float]
    status_latency_ms: Optional[float]
    remaining_latency_ms: Optional[float]
    answer_latency_ms: Optional[float]
    submit_latency_ms: Optional[float]
    error: Optional[str] = None


@dataclass
class ExamPhase:
    size: int
    exam_id: int
    question_id: int
    correct_option_id: int
    exam_title: str
    access_token: str
    seb_config_key_hash: str
    seb_browser_exam_key: str


@dataclass
class LoadContext:
    base_url: str
    report_dir: Path
    session: requests.Session
    compose_file: Optional[str]
    api_service: str
    db_service: str
    redis_service: str
    db_user: str
    db_name: str
    artifacts: Dict[str, str]
    summary: Dict[str, Any]
    admin_token: str
    admin_user: Dict[str, Any]
    common_password: str
    teacher: Dict[str, Any]
    teacher_token: str
    students: List[Participant]
    cleanup_mode: str
    minimum_apk_token: str
    app_signature: str
    original_allow_browser_testing: bool
    browser_testing_toggled: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def percentile(values: Sequence[float], ratio: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0.0, min(1.0, ratio)) * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def summarize_latencies(values: Sequence[Optional[float]]) -> Dict[str, Optional[float]]:
    filtered = [float(v) for v in values if v is not None]
    if not filtered:
        return {
            "count": 0,
            "avg_ms": None,
            "p50_ms": None,
            "p95_ms": None,
            "max_ms": None,
        }
    return {
        "count": len(filtered),
        "avg_ms": round(statistics.mean(filtered), 2),
        "p50_ms": round(percentile(filtered, 0.50) or 0.0, 2),
        "p95_ms": round(percentile(filtered, 0.95) or 0.0, 2),
        "max_ms": round(max(filtered), 2),
    }


def ensure_success(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _parse_v2_variant_map(raw_value: str, prefix: str) -> Optional[Dict[str, str]]:
    marker = f"{prefix}:"
    if not raw_value or not raw_value.startswith(marker):
        return None
    payload = raw_value[len(marker):].strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    normalized: Dict[str, str] = {}
    for key, value in parsed.items():
        key_text = str(key).strip().lower()
        value_text = str(value).strip()
        if key_text and value_text:
            normalized[key_text] = value_text
    return normalized or None


def resolve_minimum_apk_token(raw_value: str) -> Tuple[str, str]:
    raw_value = str(raw_value or "").strip()
    if not raw_value:
        return "", "empty"

    v2_map = _parse_v2_variant_map(raw_value, "TOKENS_V2")
    if v2_map:
        for key in ("new_update", "stable", "latest"):
            value = v2_map.get(key)
            if value:
                return value, f"system_v2:{key}"
        for value in v2_map.values():
            if value:
                return value, "system_v2:first"

    return raw_value, "system"


def resolve_allowed_signatures(raw_value: str) -> Tuple[List[str], str]:
    raw_value = str(raw_value or "").strip()
    if not raw_value:
        return [], "empty"

    candidates: List[str] = []
    source = "system"

    v2_map = _parse_v2_variant_map(raw_value, "SIGS_V2")
    if v2_map:
        source = "system_v2"
        for key in ("new_update", "stable", "latest"):
            value = v2_map.get(key)
            if value:
                candidates.append(value)
        for value in v2_map.values():
            if value and value not in candidates:
                candidates.append(value)
    else:
        for item in raw_value.split(","):
            cleaned = item.strip()
            if cleaned:
                candidates.append(cleaned)

    normalized: List[str] = []
    for candidate in candidates:
        lowered = candidate.strip().lower()
        if APP_SIGNATURE_RE.fullmatch(lowered):
            normalized.append(lowered)
    return normalized, source


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Concurrent production exam load test")
    parser.add_argument("--base-url", default="http://127.0.0.1", help="Base URL target")
    parser.add_argument("--admin-username", default="admin", help="Admin username")
    parser.add_argument("--admin-password", default=os.getenv("LOADTEST_ADMIN_PASSWORD"), help="Admin password")
    parser.add_argument("--admin-token", default=os.getenv("LOADTEST_ADMIN_TOKEN"), help="Pre-generated admin token")
    parser.add_argument(
        "--bootstrap-admin-token-via-docker",
        action="store_true",
        help="Generate admin token directly from API container on the same host",
    )
    parser.add_argument("--compose-file", default="docker-compose.production.yml", help="docker compose file path")
    parser.add_argument("--api-service", default="api", help="Compose API service name")
    parser.add_argument("--db-service", default="db", help="Compose DB service name")
    parser.add_argument("--redis-service", default="redis", help="Compose Redis service name")
    parser.add_argument("--db-user", default="examuser", help="DB username for cleanup/snapshots")
    parser.add_argument("--db-name", default="siab1", help="DB name for cleanup/snapshots")
    parser.add_argument("--teacher-prefix", default="loadtest_teacher", help="Temporary teacher username prefix")
    parser.add_argument("--student-prefix", default="loadtest_student", help="Temporary student username prefix")
    parser.add_argument("--class-prefix", default="LOAD620", help="Temporary class prefix")
    parser.add_argument("--common-password", default="LoadTemp#2026", help="Temporary password for teacher/students")
    parser.add_argument("--student-count", type=int, default=620, help="Total temporary students to provision")
    parser.add_argument(
        "--skip-provision",
        action="store_true",
        help="Skip teacher/student provisioning and reuse existing class/users",
    )
    parser.add_argument(
        "--reuse-student-class",
        default="",
        help="Existing student class to reuse when --skip-provision enabled",
    )
    parser.add_argument(
        "--reuse-teacher-username",
        default="",
        help="Existing teacher username to reuse when --skip-provision enabled",
    )
    parser.add_argument(
        "--reuse-teacher-password",
        default="",
        help="Existing teacher password (defaults to --common-password when empty)",
    )
    parser.add_argument(
        "--provision-strategy",
        choices=("auto", "batch", "single"),
        default="auto",
        help="Provisioning strategy for student users",
    )
    parser.add_argument(
        "--provision-workers",
        type=int,
        default=16,
        help="Thread workers for provisioning /api/users",
    )
    parser.add_argument(
        "--provision-retries",
        type=int,
        default=3,
        help="Retry count for failed student provisioning",
    )
    parser.add_argument(
        "--provision-backoff-seconds",
        type=float,
        default=2.0,
        help="Linear backoff base seconds between provisioning retries",
    )
    parser.add_argument(
        "--provision-batch-size",
        type=int,
        default=500,
        help="Batch size for /api/users/batch-create (max 500)",
    )
    parser.add_argument("--phases", default=",".join(str(item) for item in DEFAULT_PHASES), help="Comma-separated concurrent phase sizes")
    parser.add_argument(
        "--session-rounds",
        type=int,
        default=1,
        help="Repeat phase sequence this many consecutive rounds (for long-run endurance).",
    )
    parser.add_argument("--hold-seconds", type=float, default=8.0, help="Seconds to keep sessions active before submit")
    parser.add_argument(
        "--poll-jitter-seconds",
        type=float,
        default=1.5,
        help="Max jitter before status/remaining-time poll after start",
    )
    parser.add_argument("--start-timeout", type=float, default=120.0, help="Seconds to wait for start phase before release")
    parser.add_argument("--request-timeout", type=float, default=60.0, help="HTTP timeout per request")
    parser.add_argument("--max-workers", type=int, default=0, help="Thread workers per phase; 0 means phase size")
    parser.add_argument(
        "--cleanup-mode",
        choices=("hard", "api", "none"),
        default="hard",
        help="Cleanup strategy after test",
    )
    parser.add_argument("--report-prefix", default="load_620", help="Report directory prefix")
    return parser.parse_args()


def parse_phase_sizes(raw_value: str, student_count: int) -> List[int]:
    phases: List[int] = []
    for part in raw_value.split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        value = int(cleaned)
        if value <= 0:
            raise ValueError(f"phase invalid: {value}")
        if value > student_count:
            raise ValueError(f"phase {value} melebihi student-count {student_count}")
        phases.append(value)
    if not phases:
        raise ValueError("minimal ada satu phase")
    return phases


def build_phase_artifact_prefix(phase_index: int, phase_size: int) -> str:
    safe_index = max(1, int(phase_index))
    safe_size = max(1, int(phase_size))
    return f"phase_{safe_index:02d}_{safe_size:04d}"


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return session


def request_json(
    session: requests.Session,
    base_url: str,
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    expected: Iterable[int] = (200, 201),
    timeout: float = 60.0,
) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    request_headers: Dict[str, str] = {}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    if headers:
        request_headers.update(headers)
    expected_set = set(expected)

    max_attempts = 3
    transport_backoff = 0.25
    status_backoff = 0.2
    last_transport_exc: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = session.request(
                method=method,
                url=url,
                json=payload,
                data=data,
                files=files,
                headers=request_headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_transport_exc = exc
            if attempt < max_attempts:
                time.sleep(transport_backoff * attempt)
                continue
            raise

        body_text = response.text
        try:
            body: Any = response.json() if body_text else None
        except Exception:
            body = body_text

        if response.status_code in expected_set:
            return body

        if response.status_code in RETRYABLE_HTTP_STATUS and attempt < max_attempts:
            time.sleep(status_backoff * attempt)
            continue

        raise ApiError(method, path, response.status_code, body)

    if last_transport_exc is not None:
        raise last_transport_exc
    raise RuntimeError(f"{method} {path} failed without response")


def request_bytes(
    session: requests.Session,
    base_url: str,
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    expected: Iterable[int] = (200,),
    timeout: float = 60.0,
) -> bytes:
    url = f"{base_url.rstrip('/')}{path}"
    request_headers: Dict[str, str] = {}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    if headers:
        request_headers.update(headers)

    expected_set = set(expected)
    max_attempts = 3
    last_transport_exc: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.request(
                method=method,
                url=url,
                headers=request_headers,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_transport_exc = exc
            if attempt < max_attempts:
                time.sleep(0.25 * attempt)
                continue
            raise

        if response.status_code in expected_set:
            return response.content

        body_text = response.text
        try:
            body: Any = response.json() if body_text else None
        except Exception:
            body = body_text

        if response.status_code in RETRYABLE_HTTP_STATUS and attempt < max_attempts:
            time.sleep(0.2 * attempt)
            continue

        raise ApiError(method, path, response.status_code, body)

    if last_transport_exc is not None:
        raise last_transport_exc
    raise RuntimeError(f"{method} {path} bytes request failed without response")


def timed_request(*args: Any, **kwargs: Any) -> Tuple[Any, float]:
    started = time.perf_counter()
    result = request_json(*args, **kwargs)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return result, elapsed_ms


def run_command(
    cmd: List[str],
    *,
    input_text: Optional[str] = None,
    timeout: float = 120.0,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            "Command failed: "
            + " ".join(cmd)
            + f"\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def bootstrap_admin_token_via_docker(
    compose_file: str,
    api_service: str,
    username: str,
) -> Tuple[str, Dict[str, Any]]:
    python_code = f'''
import asyncio
import json
from sqlalchemy import select
from app.database import async_session_read
from app.models.user import User
from app.core.security import create_access_token

USERNAME = {username!r}

async def main():
    async with async_session_read() as db:
        result = await db.execute(select(User).where(User.username == USERNAME))
        user = result.scalar_one_or_none()
        if user is None:
            raise SystemExit(f"admin user not found: {{USERNAME}}")
        token = create_access_token({{"sub": str(user.id), "username": user.username, "role": user.role}})
        print(json.dumps({{
            "access_token": token,
            "user": {{
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "role": user.role,
            }},
        }}))

asyncio.run(main())
'''
    result = run_command(
        ["docker", "compose", "-f", compose_file, "exec", "-T", api_service, "python", "-"],
        input_text=python_code,
        timeout=120.0,
    )
    payload = json.loads(result.stdout.strip())
    return payload["access_token"], payload["user"]


def psql_json(compose_file: str, db_service: str, db_user: str, db_name: str, sql: str) -> Any:
    result = run_command(
        [
            "docker",
            "compose",
            "-f",
            compose_file,
            "exec",
            "-T",
            db_service,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            db_user,
            "-d",
            db_name,
            "-At",
            "-c",
            sql,
        ],
        timeout=120.0,
    )
    raw = result.stdout.strip()
    return json.loads(raw) if raw else None


def psql_exec(compose_file: str, db_service: str, db_user: str, db_name: str, sql: str) -> None:
    run_command(
        [
            "docker",
            "compose",
            "-f",
            compose_file,
            "exec",
            "-T",
            db_service,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            db_user,
            "-d",
            db_name,
            "-c",
            sql,
        ],
        timeout=120.0,
    )


def get_public_tables(compose_file: str, db_service: str, db_user: str, db_name: str) -> set[str]:
    sql = (
        "SELECT coalesce(json_agg(table_name ORDER BY table_name), '[]'::json) "
        "FROM information_schema.tables WHERE table_schema = 'public'"
    )
    tables = psql_json(compose_file, db_service, db_user, db_name, sql)
    return set(str(item) for item in tables or [])


def collect_db_snapshot(
    compose_file: Optional[str],
    db_service: str,
    db_user: str,
    db_name: str,
    exam_id: int,
) -> Dict[str, Any]:
    if not compose_file:
        return {"available": False, "reason": "compose_file not configured"}
    sql = f"""
    SELECT json_build_object(
        'exam_id', {exam_id},
        'status_counts', COALESCE(
            (
                SELECT json_object_agg(status, cnt)
                FROM (
                    SELECT status, count(*)::int AS cnt
                    FROM exam_sessions
                    WHERE exam_id = {exam_id}
                    GROUP BY status
                ) AS grouped
            ),
            '{{}}'::json
        ),
        'idle_in_transaction', COALESCE(
            (SELECT count(*)::int FROM pg_stat_activity WHERE datname = '{db_name}' AND state = 'idle in transaction'),
            0
        ),
        'idle_in_transaction_stale', COALESCE(
            (
                SELECT count(*)::int
                FROM pg_stat_activity
                WHERE datname = '{db_name}'
                  AND state = 'idle in transaction'
                  AND xact_start IS NOT NULL
                  AND now() - xact_start > interval '45 seconds'
            ),
            0
        ),
        'db_connections_total', COALESCE(
            (SELECT count(*)::int FROM pg_stat_activity WHERE datname = '{db_name}'),
            0
        )
    )
    """
    try:
        payload = psql_json(compose_file, db_service, db_user, db_name, sql)
        return payload if isinstance(payload, dict) else {"raw": payload}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def load_students_from_db(
    compose_file: str,
    db_service: str,
    db_user: str,
    db_name: str,
    student_class: str,
    limit: int,
) -> List[Dict[str, Any]]:
    safe_class = student_class.replace("'", "''")
    safe_limit = max(1, limit)
    sql = f"""
    SELECT COALESCE(
      json_agg(
        json_build_object(
          'id', id,
          'username', username,
          'full_name', full_name,
          'student_class', student_class
        )
        ORDER BY username
      ),
      '[]'::json
    )
    FROM (
      SELECT id, username, full_name, student_class
      FROM users
      WHERE role = 'student'
        AND student_class = '{safe_class}'
      ORDER BY username
      LIMIT {safe_limit}
    ) AS filtered
    """
    payload = psql_json(compose_file, db_service, db_user, db_name, sql)
    if isinstance(payload, list):
        return payload
    return []


def wait_for_clean_db(
    compose_file: Optional[str],
    db_service: str,
    db_user: str,
    db_name: str,
    *,
    timeout_seconds: float = 30.0,
    poll_interval: float = 1.0,
) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_snapshot: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_snapshot = collect_db_snapshot(compose_file, db_service, db_user, db_name, exam_id=0)
        idle_tx = int(last_snapshot.get("idle_in_transaction") or 0)
        if idle_tx == 0:
            last_snapshot["clean"] = True
            return last_snapshot
        time.sleep(max(0.1, poll_interval))
    last_snapshot["clean"] = False
    return last_snapshot


def collect_redis_snapshot(compose_file: Optional[str], redis_service: str) -> Dict[str, Any]:
    if not compose_file:
        return {"available": False, "reason": "compose_file not configured"}
    try:
        result = run_command(
            ["docker", "compose", "-f", compose_file, "exec", "-T", redis_service, "redis-cli", "INFO", "stats"],
            timeout=60.0,
        )
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    wanted = {
        "instantaneous_ops_per_sec",
        "rejected_connections",
        "evicted_keys",
        "keyspace_hits",
        "keyspace_misses",
    }
    parsed: Dict[str, Any] = {"available": True}
    for line in result.stdout.splitlines():
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key in wanted:
            try:
                parsed[key] = int(value.strip())
            except ValueError:
                parsed[key] = value.strip()
    return parsed


def write_json(report_dir: Path, artifacts: Dict[str, str], name: str, payload: Any) -> str:
    path = report_dir / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    artifacts[name] = str(path)
    return str(path)


def build_student_payloads(prefix: str, stamp: str, count: int, class_name: str, password: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index in range(1, count + 1):
        username = f"{prefix}_{stamp}_{index:03d}"
        full_name = f"Load Test Student {index:03d}"
        rows.append({
            "username": username,
            "password": password,
            "full_name": full_name,
            "role": "student",
            "student_class": class_name,
        })
    return rows


def create_user_via_admin(
    base_url: str,
    admin_token: str,
    payload: Dict[str, Any],
    timeout: float,
) -> ProvisionResult:
    started = time.perf_counter()
    worker_session = new_session()
    try:
        result = request_json(
            worker_session,
            base_url,
            "POST",
            "/api/users",
            token=admin_token,
            payload=payload,
            expected=(200, 201),
            timeout=timeout,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return ProvisionResult(
            username=str(payload["username"]),
            ok=True,
            latency_ms=latency_ms,
            user_id=int(result["id"]),
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return ProvisionResult(
            username=str(payload["username"]),
            ok=False,
            latency_ms=latency_ms,
            error=str(exc),
        )
    finally:
        worker_session.close()


def provision_students(
    base_url: str,
    admin_token: str,
    payloads: Sequence[Dict[str, Any]],
    timeout: float,
    max_workers: int,
) -> List[ProvisionResult]:
    results: List[ProvisionResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(create_user_via_admin, base_url, admin_token, payload, timeout)
            for payload in payloads
        ]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item.username)
    return results


def _batch_error_username(raw_error: str, payloads: Sequence[Dict[str, Any]]) -> Optional[str]:
    row_match = re.search(r"Row\s+(\d+):", raw_error)
    if row_match:
        row_number = int(row_match.group(1))
        index = row_number - 1
        if 0 <= index < len(payloads):
            return str(payloads[index].get("username") or "")

    user_match = re.search(r"\(([^()]+)\)\s*$", raw_error.strip())
    if user_match:
        candidate = user_match.group(1).strip()
        if candidate:
            return candidate
    return None


def provision_students_batch(
    session: requests.Session,
    base_url: str,
    admin_token: str,
    payloads: Sequence[Dict[str, Any]],
    timeout: float,
    batch_size: int,
) -> List[ProvisionResult]:
    safe_batch_size = max(1, min(500, batch_size))
    results: List[ProvisionResult] = []
    for batch in chunked(list(payloads), safe_batch_size):
        started = time.perf_counter()
        try:
            payload = request_json(
                session,
                base_url,
                "POST",
                "/api/users/batch-create",
                token=admin_token,
                payload=batch,
                expected=(200,),
                timeout=max(timeout, 120.0),
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            created = {
                str(item).strip()
                for item in (payload.get("created_usernames") or [])
                if str(item).strip()
            }
            errors = [str(item) for item in (payload.get("errors") or [])]
            error_map: Dict[str, str] = {}
            for raw_error in errors:
                username = _batch_error_username(raw_error, batch)
                if username:
                    error_map[username] = raw_error

            for row in batch:
                username = str(row["username"])
                if username in created:
                    results.append(
                        ProvisionResult(
                            username=username,
                            ok=True,
                            latency_ms=elapsed_ms,
                        )
                    )
                else:
                    results.append(
                        ProvisionResult(
                            username=username,
                            ok=False,
                            latency_ms=elapsed_ms,
                            error=error_map.get(username, "not created by batch endpoint"),
                        )
                    )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            for row in batch:
                results.append(
                    ProvisionResult(
                        username=str(row["username"]),
                        ok=False,
                        latency_ms=elapsed_ms,
                        error=str(exc),
                    )
                )
    results.sort(key=lambda item: item.username)
    return results


def chunked(values: Sequence[int], size: int) -> Iterable[List[int]]:
    for index in range(0, len(values), size):
        yield list(values[index:index + size])


def create_teacher(
    session: requests.Session,
    base_url: str,
    admin_token: str,
    username: str,
    password: str,
    timeout: float,
) -> Dict[str, Any]:
    return request_json(
        session,
        base_url,
        "POST",
        "/api/users",
        token=admin_token,
        payload={
            "username": username,
            "password": password,
            "full_name": "Load Test Teacher",
            "role": "teacher",
        },
        expected=(200, 201),
        timeout=timeout,
    )


def login_user(
    base_url: str,
    username: str,
    password: str,
    timeout: float,
    *,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[str, Dict[str, Any]]:
    session = new_session()
    try:
        payload = request_json(
            session,
            base_url,
            "POST",
            "/api/auth/signin",
            payload={"username": username, "password": password},
            headers=headers,
            expected=(200,),
            timeout=timeout,
        )
    finally:
        session.close()
    return payload["access_token"], payload["user"]


def resolve_admin_identity(args: argparse.Namespace, session: requests.Session) -> Tuple[str, Dict[str, Any]]:
    if args.admin_token:
        user = request_json(
            session,
            args.base_url,
            "GET",
            "/api/auth/me",
            token=args.admin_token,
            expected=(200,),
            timeout=args.request_timeout,
        )
        return args.admin_token, user

    if args.admin_password:
        return login_user(args.base_url, args.admin_username, args.admin_password, args.request_timeout)

    if args.bootstrap_admin_token_via_docker:
        compose_file = str(Path(args.compose_file))
        return bootstrap_admin_token_via_docker(compose_file, args.api_service, args.admin_username)

    raise RuntimeError(
        "Admin credential tidak tersedia. Isi --admin-password atau pakai --bootstrap-admin-token-via-docker."
    )


def update_browser_testing(
    session: requests.Session,
    base_url: str,
    admin_token: str,
    enabled: bool,
    timeout: float,
) -> Dict[str, Any]:
    return request_json(
        session,
        base_url,
        "PUT",
        "/api/v1/settings/system",
        token=admin_token,
        payload={"allow_browser_testing": enabled},
        expected=(200,),
        timeout=timeout,
    )


def download_exam_seb_keys(ctx: LoadContext, exam_id: int, timeout: float) -> Tuple[str, str]:
    try:
        config_bytes = request_bytes(
            ctx.session,
            ctx.base_url,
            "GET",
            f"/api/exams/{exam_id}/seb-config.seb",
            token=ctx.teacher_token,
            expected=(200,),
            timeout=timeout,
        )
        parsed = plistlib.loads(config_bytes)
        config_key = str(parsed.get("configKey") or "")
        browser_exam_key = str(parsed.get("browserExamKey") or "")
    except ApiError as exc:
        detail = exc.body.get("detail") if isinstance(exc.body, dict) else None
        feature_disabled = (
            exc.status == 404
            and isinstance(detail, dict)
            and detail.get("error") == "FEATURE_DISABLED"
            and detail.get("feature") == "seb_desktop_legacy"
        )
        if not feature_disabled or not ctx.compose_file:
            raise
        parsed = psql_json(
            ctx.compose_file,
            ctx.db_service,
            ctx.db_user,
            ctx.db_name,
            "SELECT json_build_object("
            "'configKey', seb_config_key, "
            "'browserExamKey', seb_browser_exam_key"
            f") FROM exams WHERE id = {int(exam_id)}",
        )
        config_key = str((parsed or {}).get("configKey") or "")
        browser_exam_key = str((parsed or {}).get("browserExamKey") or "")
    ensure_success(bool(config_key), f"configKey kosong untuk exam {exam_id}")
    ensure_success(bool(browser_exam_key), f"browserExamKey kosong untuk exam {exam_id}")
    config_key_hash = hashlib.sha256(config_key.encode()).hexdigest()
    return config_key_hash, browser_exam_key


def build_mobile_headers(build_token: str, app_signature: str) -> Dict[str, str]:
    return {
        "User-Agent": "SXB-Client/1.0",
        "X-Build-Token": build_token,
        "X-App-Signature": app_signature,
        "X-App-Timestamp": str(int(time.time())),
    }


def build_seb_headers(
    base_url: str,
    path: str,
    config_key_hash: str,
    browser_exam_key: str,
) -> Dict[str, str]:
    request_url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request_hash = hmac.new(
        browser_exam_key.encode(),
        request_url.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "User-Agent": "Safe Exam Browser/3.6.0",
        "X-SafeExamBrowser-ConfigKeyHash": config_key_hash,
        "X-SafeExamBrowser-RequestHash": request_hash,
    }


def _seb_request_url_candidates(base_url: str, path: str) -> List[str]:
    """
    Build deterministic URL candidates for SEB request-hash verification.

    In reverse-proxy deployments, backend verification can observe HTTP scheme
    while clients call HTTPS. We try both normalized forms to avoid false
    INVALID_REQUEST_HASH failures in load tests.
    """
    primary = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    parsed = urlparse(primary)

    candidates: List[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        if url and url not in seen:
            seen.add(url)
            candidates.append(url)

    add(primary)

    if parsed.scheme in {"http", "https"}:
        alt_scheme = "http" if parsed.scheme == "https" else "https"
        add(urlunparse(parsed._replace(scheme=alt_scheme)))

    # Explicit default port variations (in case upstream preserves Host:port).
    if parsed.hostname and parsed.scheme in {"http", "https"}:
        if parsed.scheme == "https":
            add(urlunparse(parsed._replace(netloc=f"{parsed.hostname}:443")))
            add(urlunparse(parsed._replace(scheme="http", netloc=f"{parsed.hostname}:80")))
        else:
            add(urlunparse(parsed._replace(netloc=f"{parsed.hostname}:80")))
            add(urlunparse(parsed._replace(scheme="https", netloc=f"{parsed.hostname}:443")))

    return candidates


def build_seb_header_candidates(
    base_url: str,
    path: str,
    config_key_hash: str,
    browser_exam_key: str,
) -> List[Dict[str, str]]:
    headers: List[Dict[str, str]] = []
    for request_url in _seb_request_url_candidates(base_url, path):
        request_hash = hmac.new(
            browser_exam_key.encode(),
            request_url.encode(),
            hashlib.sha256,
        ).hexdigest()
        headers.append(
            {
                "User-Agent": "Safe Exam Browser/3.6.0",
                "X-SafeExamBrowser-ConfigKeyHash": config_key_hash,
                "X-SafeExamBrowser-RequestHash": request_hash,
            }
        )

    # Safety fallback for environments where request hash is not enforced.
    headers.append(
        {
            "User-Agent": "Safe Exam Browser/3.6.0",
            "X-SafeExamBrowser-ConfigKeyHash": config_key_hash,
        }
    )
    return headers


def _is_invalid_request_hash_error(exc: Exception) -> bool:
    if not isinstance(exc, ApiError):
        return False
    if exc.status != 403:
        return False
    body = exc.body
    if not isinstance(body, dict):
        return False
    detail = body.get("detail")
    if not isinstance(detail, dict):
        return False
    return str(detail.get("error") or "").strip().upper() == "INVALID_REQUEST_HASH"


def timed_request_with_seb_hash_retry(
    session: requests.Session,
    base_url: str,
    method: str,
    path: str,
    *,
    token: str,
    payload: Dict[str, Any],
    config_key_hash: str,
    browser_exam_key: str,
    expected: Iterable[int],
    timeout: float,
) -> Tuple[Any, float]:
    header_candidates = build_seb_header_candidates(
        base_url=base_url,
        path=path,
        config_key_hash=config_key_hash,
        browser_exam_key=browser_exam_key,
    )
    last_exc: Optional[Exception] = None
    for index, headers in enumerate(header_candidates):
        try:
            return timed_request(
                session,
                base_url,
                method,
                path,
                token=token,
                payload=payload,
                headers=headers,
                expected=expected,
                timeout=timeout,
            )
        except Exception as exc:
            last_exc = exc
            if _is_invalid_request_hash_error(exc) and index < len(header_candidates) - 1:
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("SEB hash retry failed without captured error")


def create_exam_phase(
    ctx: LoadContext,
    phase_size: int,
    phase_index: int,
    class_name: str,
    stamp: str,
    timeout: float,
    created_exam_ids: Optional[List[int]] = None,
) -> ExamPhase:
    now = utc_now()
    exam = request_json(
        ctx.session,
        ctx.base_url,
        "POST",
        "/api/exams",
        token=ctx.teacher_token,
        payload={
            "title": f"Load Test S{phase_index:02d} {stamp} {phase_size}",
            "description": f"Temporary concurrent load test phase {phase_size} (run {phase_index})",
            "duration_minutes": 45,
            "start_time": iso_z(now - timedelta(minutes=5)),
            "end_time": iso_z(now + timedelta(minutes=55)),
            "passing_score": 0,
            "max_attempts": 1,
            "shuffle_questions": False,
            "shuffle_options": False,
            "show_results": True,
            "allow_review": False,
            "is_published": False,
            "allowed_classes": class_name,
        },
        expected=(200, 201),
        timeout=timeout,
    )
    exam_id = int(exam["id"])
    if created_exam_ids is not None:
        created_exam_ids.append(exam_id)
    question = request_json(
        ctx.session,
        ctx.base_url,
        "POST",
        f"/api/questions/{exam_id}",
        token=ctx.teacher_token,
        payload={
            "question_text": f"Phase {phase_size} (run {phase_index}): 2 + 2 = ?",
            "question_type": "multiple_choice",
            "difficulty_level": "easy",
            "points": 1,
            "order_index": 1,
            "options": [
                {"option_text": "3", "is_correct": False, "order_index": 1},
                {"option_text": "4", "is_correct": True, "order_index": 2},
            ],
        },
        expected=(200, 201),
        timeout=timeout,
    )
    request_json(
        ctx.session,
        ctx.base_url,
        "POST",
        f"/api/exams/{exam_id}/publish",
        token=ctx.teacher_token,
        expected=(200,),
        timeout=timeout,
    )
    seb_config_key_hash, seb_browser_exam_key = download_exam_seb_keys(
        ctx,
        exam_id,
        timeout,
    )
    correct_option_id = next(int(item["id"]) for item in question["options"] if item.get("is_correct"))
    return ExamPhase(
        size=phase_size,
        exam_id=exam_id,
        question_id=int(question["id"]),
        correct_option_id=correct_option_id,
        exam_title=str(exam["title"]),
        access_token=str(exam["access_token"]),
        seb_config_key_hash=seb_config_key_hash,
        seb_browser_exam_key=seb_browser_exam_key,
    )


def login_participant(base_url: str, participant: Participant, password: str, timeout: float) -> LoginResult:
    started = time.perf_counter()
    worker_session = new_session()
    try:
        payload = request_json(
            worker_session,
            base_url,
            "POST",
            "/api/auth/signin",
            payload={"username": participant.username, "password": password},
            expected=(200,),
            timeout=timeout,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return LoginResult(
            participant=participant,
            ok=True,
            token=str(payload["access_token"]),
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return LoginResult(
            participant=participant,
            ok=False,
            token=None,
            latency_ms=latency_ms,
            error=str(exc),
        )
    finally:
        worker_session.close()


def login_participant_with_mobile_headers(
    base_url: str,
    participant: Participant,
    password: str,
    timeout: float,
    *,
    build_token: str,
    app_signature: str,
) -> LoginResult:
    started = time.perf_counter()
    worker_session = new_session()
    try:
        payload = request_json(
            worker_session,
            base_url,
            "POST",
            "/api/auth/signin",
            payload={"username": participant.username, "password": password},
            headers=build_mobile_headers(build_token, app_signature),
            expected=(200,),
            timeout=timeout,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return LoginResult(
            participant=participant,
            ok=True,
            token=str(payload["access_token"]),
            latency_ms=latency_ms,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return LoginResult(
            participant=participant,
            ok=False,
            token=None,
            latency_ms=latency_ms,
            error=str(exc),
        )
    finally:
        worker_session.close()


class StartTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_sessions: List[int] = []
        self.started_users: List[int] = []
        self.ready_sessions: List[int] = []
        self.ready_users: List[int] = []

    def add(self, user_id: int, session_id: int) -> None:
        with self._lock:
            self.started_users.append(user_id)
            self.started_sessions.append(session_id)

    def mark_ready(self, user_id: int, session_id: int) -> None:
        with self._lock:
            self.ready_users.append(user_id)
            self.ready_sessions.append(session_id)

    def snapshot(self) -> Dict[str, List[int]]:
        with self._lock:
            return {
                "started_users": list(self.started_users),
                "started_sessions": list(self.started_sessions),
                "ready_users": list(self.ready_users),
                "ready_sessions": list(self.ready_sessions),
            }


def run_exam_flow(
    base_url: str,
    participant: Participant,
    token: str,
    phase: ExamPhase,
    release_event: threading.Event,
    tracker: StartTracker,
    timeout: float,
    poll_jitter_seconds: float,
    release_wait_timeout: float,
) -> ExamFlowResult:
    worker_session = new_session()
    session_id: Optional[int] = None
    start_latency_ms: Optional[float] = None
    status_latency_ms: Optional[float] = None
    remaining_latency_ms: Optional[float] = None
    answer_latency_ms: Optional[float] = None
    submit_latency_ms: Optional[float] = None
    try:
        start_payload, start_latency_ms = timed_request_with_seb_hash_retry(
            worker_session,
            base_url,
            "POST",
            f"/api/exams/{phase.exam_id}/start",
            token=token,
            payload={},
            config_key_hash=phase.seb_config_key_hash,
            browser_exam_key=phase.seb_browser_exam_key,
            expected=(200,),
            timeout=timeout,
        )
        session_id = int(start_payload["session_id"])
        tracker.add(participant.user_id, session_id)

        if poll_jitter_seconds > 0:
            jitter_fraction = (participant.user_id % 17) / 16.0
            time.sleep(poll_jitter_seconds * jitter_fraction)

        _, status_latency_ms = timed_request(
            worker_session,
            base_url,
            "GET",
            f"/api/exams/session/{session_id}/status",
            token=token,
            headers={"User-Agent": "Safe Exam Browser/3.6.0"},
            expected=(200,),
            timeout=timeout,
        )
        _, remaining_latency_ms = timed_request(
            worker_session,
            base_url,
            "GET",
            f"/api/exams/session/{session_id}/remaining-time",
            token=token,
            headers={"User-Agent": "Safe Exam Browser/3.6.0"},
            expected=(200,),
            timeout=timeout,
        )
        tracker.mark_ready(participant.user_id, session_id)

        released = release_event.wait(timeout=release_wait_timeout)
        if not released:
            raise RuntimeError("release_event timeout")

        _, answer_latency_ms = timed_request_with_seb_hash_retry(
            worker_session,
            base_url,
            "POST",
            "/api/exams/submit-answer",
            token=token,
            payload={
                "session_id": session_id,
                "question_id": phase.question_id,
                "selected_option_id": phase.correct_option_id,
            },
            config_key_hash=phase.seb_config_key_hash,
            browser_exam_key=phase.seb_browser_exam_key,
            expected=(200,),
            timeout=timeout,
        )
        _, submit_latency_ms = timed_request_with_seb_hash_retry(
            worker_session,
            base_url,
            "POST",
            "/api/exams/submit",
            token=token,
            payload={"session_id": session_id, "force_submit": False},
            config_key_hash=phase.seb_config_key_hash,
            browser_exam_key=phase.seb_browser_exam_key,
            expected=(200,),
            timeout=timeout,
        )
        return ExamFlowResult(
            participant=participant,
            session_id=session_id,
            start_ok=True,
            status_ok=True,
            remaining_ok=True,
            answer_ok=True,
            submit_ok=True,
            start_latency_ms=start_latency_ms,
            status_latency_ms=status_latency_ms,
            remaining_latency_ms=remaining_latency_ms,
            answer_latency_ms=answer_latency_ms,
            submit_latency_ms=submit_latency_ms,
        )
    except Exception as exc:
        return ExamFlowResult(
            participant=participant,
            session_id=session_id,
            start_ok=start_latency_ms is not None,
            status_ok=status_latency_ms is not None,
            remaining_ok=remaining_latency_ms is not None,
            answer_ok=answer_latency_ms is not None,
            submit_ok=submit_latency_ms is not None,
            start_latency_ms=start_latency_ms,
            status_latency_ms=status_latency_ms,
            remaining_latency_ms=remaining_latency_ms,
            answer_latency_ms=answer_latency_ms,
            submit_latency_ms=submit_latency_ms,
            error=str(exc),
        )
    finally:
        worker_session.close()


def collect_phase_logs(
    compose_file: Optional[str],
    *,
    since: Optional[str] = None,
    since_minutes: int = 10,
) -> Dict[str, Any]:
    if not compose_file:
        return {"available": False, "reason": "compose_file not configured"}
    try:
        since_value = since or f"{since_minutes}m"
        result = run_command(
            [
                "docker",
                "compose",
                "-f",
                compose_file,
                "logs",
                "--since",
                since_value,
                "--no-color",
                "api",
                "api2",
                "api3",
                "api4",
                "api5",
                "api6",
                "nginx",
                "db",
                "pgbouncer",
            ],
            timeout=120.0,
        )
        lines = result.stdout.splitlines()
        return {
            "available": True,
            "tail": lines[-400:],
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def run_login_phase(
    participants: Sequence[Participant],
    password: str,
    base_url: str,
    timeout: float,
    max_workers: int,
    *,
    build_token: str,
    app_signature: str,
) -> List[LoginResult]:
    results: List[LoginResult] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                login_participant_with_mobile_headers,
                base_url,
                participant,
                password,
                timeout,
                build_token=build_token,
                app_signature=app_signature,
            )
            for participant in participants
        ]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item.participant.username)
    return results


def run_exam_phase(
    ctx: LoadContext,
    phase: ExamPhase,
    participants: Sequence[Participant],
    phase_index: int,
    timeout: float,
    start_timeout: float,
    hold_seconds: float,
    max_workers: int,
    poll_jitter_seconds: float,
) -> Dict[str, Any]:
    phase_prefix = build_phase_artifact_prefix(phase_index, phase.size)
    phase_report: Dict[str, Any] = {
        "phase_index": phase_index,
        "phase_tag": phase_prefix,
        "phase_size": phase.size,
        "exam_id": phase.exam_id,
        "question_id": phase.question_id,
        "exam_title": phase.exam_title,
    }
    phase_report["db_precheck"] = wait_for_clean_db(
        ctx.compose_file,
        ctx.db_service,
        ctx.db_user,
        ctx.db_name,
    )

    login_results = run_login_phase(
        participants=participants,
        password=ctx.common_password,
        base_url=ctx.base_url,
        timeout=timeout,
        max_workers=max_workers,
        build_token=ctx.minimum_apk_token,
        app_signature=ctx.app_signature,
    )
    successful_logins = [item for item in login_results if item.ok and item.token]
    phase_report["login"] = {
        "success_count": len(successful_logins),
        "failure_count": len(login_results) - len(successful_logins),
        "latency": summarize_latencies([item.latency_ms for item in login_results]),
        "errors": [
            {"username": item.participant.username, "error": item.error}
            for item in login_results if not item.ok
        ][:50],
    }
    write_json(ctx.report_dir, ctx.artifacts, f"{phase_prefix}_login_results.json", [asdict(item) for item in login_results])

    tracker = StartTracker()
    release_event = threading.Event()
    exam_results: List[ExamFlowResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        release_wait_timeout = max(start_timeout + hold_seconds + timeout + 60.0, 300.0)
        future_map = {
            executor.submit(
                run_exam_flow,
                ctx.base_url,
                item.participant,
                item.token or "",
                phase,
                release_event,
                tracker,
                timeout,
                poll_jitter_seconds,
                release_wait_timeout,
            ): item.participant.username
            for item in successful_logins
        }

        deadline = time.monotonic() + start_timeout
        while time.monotonic() < deadline:
            tracker_snapshot = tracker.snapshot()
            ready_count = len(tracker_snapshot["ready_sessions"])
            finished_count = sum(1 for future in future_map if future.done())
            if ready_count >= len(successful_logins):
                break
            # Some workers can fail fast on transient 5xx before the release gate.
            # Release the successfully started sessions once every worker is either
            # ready or has already failed, instead of stalling until start_timeout.
            if ready_count + finished_count >= len(successful_logins):
                break
            if finished_count >= len(successful_logins):
                break
            time.sleep(0.2)

        started_snapshot = tracker.snapshot()
        phase_report["started_before_release"] = len(started_snapshot["started_sessions"])
        phase_report["started_user_ids"] = started_snapshot["started_users"]
        phase_report["started_session_ids"] = started_snapshot["started_sessions"]
        phase_report["ready_before_snapshot"] = len(started_snapshot["ready_sessions"])
        phase_report["ready_user_ids"] = started_snapshot["ready_users"]
        phase_report["ready_session_ids"] = started_snapshot["ready_sessions"]
        phase_report["failed_before_release"] = sum(1 for future in future_map if future.done())
        phase_report["release_wait_timeout_seconds"] = release_wait_timeout

        live_stats = request_json(
            ctx.session,
            ctx.base_url,
            "GET",
            f"/api/monitoring/exam/{phase.exam_id}/live-stats",
            token=ctx.teacher_token,
            expected=(200,),
            timeout=max(timeout, 120.0),
        )
        db_snapshot = collect_db_snapshot(
            ctx.compose_file,
            ctx.db_service,
            ctx.db_user,
            ctx.db_name,
            phase.exam_id,
        )
        redis_snapshot = collect_redis_snapshot(ctx.compose_file, ctx.redis_service)
        health_payload = request_json(
            ctx.session,
            ctx.base_url,
            "GET",
            "/health",
            expected=(200,),
            timeout=timeout,
        )

        phase_report["live_stats_during_hold"] = live_stats
        phase_report["db_snapshot_during_hold"] = db_snapshot
        phase_report["redis_snapshot_during_hold"] = redis_snapshot
        phase_report["health_during_hold"] = health_payload
        write_json(ctx.report_dir, ctx.artifacts, f"{phase_prefix}_live_stats_during_hold.json", live_stats)
        write_json(ctx.report_dir, ctx.artifacts, f"{phase_prefix}_db_snapshot_during_hold.json", db_snapshot)
        write_json(ctx.report_dir, ctx.artifacts, f"{phase_prefix}_redis_snapshot_during_hold.json", redis_snapshot)

        time.sleep(max(0.0, hold_seconds))
        release_event.set()

        for future in as_completed(list(future_map.keys())):
            exam_results.append(future.result())

    exam_results.sort(key=lambda item: item.participant.username)
    write_json(ctx.report_dir, ctx.artifacts, f"{phase_prefix}_exam_results.json", [asdict(item) for item in exam_results])

    live_stats_after_submit: Dict[str, Any] = {}
    try:
        live_stats_after_submit = request_json(
            ctx.session,
            ctx.base_url,
            "GET",
            f"/api/monitoring/exam/{phase.exam_id}/live-stats",
            token=ctx.teacher_token,
            expected=(200,),
            timeout=max(timeout, 120.0),
        )
    except Exception as exc:
        live_stats_after_submit = {
            "error": str(exc),
            "exam_id": phase.exam_id,
        }
    db_snapshot_after_submit = collect_db_snapshot(
        ctx.compose_file,
        ctx.db_service,
        ctx.db_user,
        ctx.db_name,
        phase.exam_id,
    )

    phase_report["sessions_after_submit_count"] = sum(
        int(value) for value in (db_snapshot_after_submit.get("status_counts") or {}).values()
    )
    phase_report["live_stats_after_submit"] = live_stats_after_submit
    phase_report["db_snapshot_after_submit"] = db_snapshot_after_submit
    write_json(
        ctx.report_dir,
        ctx.artifacts,
        f"{phase_prefix}_db_snapshot_after_submit.json",
        db_snapshot_after_submit,
    )

    phase_report["exam_flow"] = {
        "success_start_count": sum(1 for item in exam_results if item.start_ok),
        "success_status_count": sum(1 for item in exam_results if item.status_ok),
        "success_remaining_count": sum(1 for item in exam_results if item.remaining_ok),
        "success_answer_count": sum(1 for item in exam_results if item.answer_ok),
        "success_submit_count": sum(1 for item in exam_results if item.submit_ok),
        "start_latency": summarize_latencies([item.start_latency_ms for item in exam_results]),
        "status_latency": summarize_latencies([item.status_latency_ms for item in exam_results]),
        "remaining_latency": summarize_latencies([item.remaining_latency_ms for item in exam_results]),
        "answer_latency": summarize_latencies([item.answer_latency_ms for item in exam_results]),
        "submit_latency": summarize_latencies([item.submit_latency_ms for item in exam_results]),
        "errors": [
            {"username": item.participant.username, "error": item.error, "session_id": item.session_id}
            for item in exam_results if item.error
        ][:50],
    }

    submitted_statuses = {
        str(key): int(value)
        for key, value in (db_snapshot_after_submit.get("status_counts") or {}).items()
    }
    phase_report["session_status_counts_after_submit"] = submitted_statuses

    expected_count = len(successful_logins)
    db_during_available = db_snapshot.get("available", True) is not False
    db_after_available = db_snapshot_after_submit.get("available", True) is not False

    pass_checks = {
        "expected_login_count": expected_count == phase.size,
        "started_before_release": phase_report["started_before_release"] == phase.size,
        "ready_before_snapshot": phase_report["ready_before_snapshot"] == phase.size,
        "active_participants_during_hold": int(live_stats.get("active_participants") or 0) == phase.size,
        "success_submit_count": phase_report["exam_flow"]["success_submit_count"] == phase.size,
        # DB checks are optional when compose_file is not configured (API-only run).
        "db_idle_in_transaction_stale": (
            int(db_snapshot.get("idle_in_transaction_stale") or 0) == 0
            if db_during_available
            else True
        ),
        "db_in_progress_during_hold": (
            int((db_snapshot.get("status_counts") or {}).get("in_progress", 0)) == phase.size
            if db_during_available
            else True
        ),
        "db_submitted_after_submit": (
            int(submitted_statuses.get("submitted", 0)) == phase.size
            if db_after_available
            else int((live_stats_after_submit.get("completed_participants") or 0)) == phase.size
        ),
    }
    phase_report["pass_checks"] = pass_checks
    phase_report["pass"] = all(pass_checks.values())
    if not phase_report["pass"]:
        phase_report["diagnostic_logs"] = collect_phase_logs(
            ctx.compose_file,
            since=str(ctx.summary["created_at"]),
        )
        write_json(ctx.report_dir, ctx.artifacts, f"{phase_prefix}_diagnostic_logs.json", phase_report["diagnostic_logs"])

    return phase_report


def api_cleanup(ctx: LoadContext, exam_ids: Sequence[int], user_ids: Sequence[int]) -> Dict[str, Any]:
    details: Dict[str, Any] = {"mode": "api", "exam_ids": list(exam_ids), "user_ids": list(user_ids)}
    for exam_id in exam_ids:
        try:
            request_json(
                ctx.session,
                ctx.base_url,
                "DELETE",
                f"/api/exams/{exam_id}/results",
                token=ctx.teacher_token,
                expected=(200, 204),
                timeout=120.0,
            )
        except Exception as exc:
            details.setdefault("result_delete_errors", []).append({"exam_id": exam_id, "error": str(exc)})
        try:
            request_json(
                ctx.session,
                ctx.base_url,
                "DELETE",
                f"/api/exams/{exam_id}",
                token=ctx.teacher_token,
                expected=(200, 204),
                timeout=120.0,
            )
        except Exception as exc:
            details.setdefault("exam_delete_errors", []).append({"exam_id": exam_id, "error": str(exc)})

    for chunk in chunked(list(user_ids), 100):
        query = "&".join([f"user_ids={item}" for item in chunk] + ["permanent=true"])
        try:
            request_json(
                ctx.session,
                ctx.base_url,
                "DELETE",
                f"/api/users/batch-delete?{query}",
                token=ctx.admin_token,
                expected=(200,),
                timeout=120.0,
            )
        except Exception as exc:
            # Fallback for deployments where /api/users/{user_id} shadows
            # /api/users/batch-delete and returns 422 int-parsing error.
            fallback_applied = False
            if isinstance(exc, ApiError) and int(exc.status) == 422:
                try:
                    request_json(
                        ctx.session,
                        ctx.base_url,
                        "PATCH",
                        "/api/users/batch-update",
                        token=ctx.admin_token,
                        payload={"user_ids": list(chunk), "update_data": {"is_active": False}},
                        expected=(200,),
                        timeout=120.0,
                    )
                    fallback_applied = True
                    details.setdefault("user_delete_fallback", []).append(
                        {"user_ids": list(chunk), "mode": "soft_deactivate_batch_update"}
                    )
                except Exception as fallback_exc:
                    details.setdefault("user_delete_errors", []).append(
                        {"user_ids": chunk, "error": str(fallback_exc)}
                    )
            if not fallback_applied:
                details.setdefault("user_delete_errors", []).append({"user_ids": chunk, "error": str(exc)})
    return details


def hard_cleanup(ctx: LoadContext, exam_ids: Sequence[int], user_ids: Sequence[int]) -> Dict[str, Any]:
    ensure_success(bool(ctx.compose_file), "hard cleanup but compose_file kosong")
    exam_list = ",".join(str(int(item)) for item in exam_ids)
    user_list = ",".join(str(int(item)) for item in user_ids)
    tables = get_public_tables(ctx.compose_file or "", ctx.db_service, ctx.db_user, ctx.db_name)
    executed: List[str] = []

    def maybe_exec(table: str, sql: str, label: str) -> None:
        if table in tables:
            psql_exec(ctx.compose_file or "", ctx.db_service, ctx.db_user, ctx.db_name, sql)
            executed.append(label)

    if exam_list:
        if "security_events" in tables:
            psql_exec(
                ctx.compose_file or "",
                ctx.db_service,
                ctx.db_user,
                ctx.db_name,
                f"DELETE FROM security_events WHERE session_id IN (SELECT id FROM exam_sessions WHERE exam_id IN ({exam_list}));",
            )
            executed.append("security_events_by_session")
        maybe_exec(
            "exam_logs",
            f"DELETE FROM exam_logs WHERE session_id IN (SELECT id FROM exam_sessions WHERE exam_id IN ({exam_list}));",
            "exam_logs",
        )
        maybe_exec(
            "answers",
            f"DELETE FROM answers WHERE session_id IN (SELECT id FROM exam_sessions WHERE exam_id IN ({exam_list}));",
            "answers",
        )
        maybe_exec(
            "exam_sessions",
            f"DELETE FROM exam_sessions WHERE exam_id IN ({exam_list});",
            "exam_sessions",
        )
        maybe_exec(
            "question_tags_map",
            f"DELETE FROM question_tags_map WHERE question_id IN (SELECT id FROM questions WHERE exam_id IN ({exam_list}));",
            "question_tags_map",
        )
        maybe_exec(
            "question_options",
            f"DELETE FROM question_options WHERE question_id IN (SELECT id FROM questions WHERE exam_id IN ({exam_list}));",
            "question_options",
        )
        maybe_exec(
            "questions",
            f"DELETE FROM questions WHERE exam_id IN ({exam_list});",
            "questions",
        )
        maybe_exec(
            "scheduled_publications",
            f"DELETE FROM scheduled_publications WHERE exam_id IN ({exam_list});",
            "scheduled_publications",
        )
        maybe_exec(
            "exams",
            f"DELETE FROM exams WHERE id IN ({exam_list});",
            "exams",
        )

    if user_list:
        maybe_exec(
            "notifications",
            f"DELETE FROM notifications WHERE user_id IN ({user_list});",
            "notifications",
        )
        maybe_exec(
            "user_activity_logs",
            f"DELETE FROM user_activity_logs WHERE user_id IN ({user_list});",
            "user_activity_logs",
        )
        if "security_events" in tables:
            psql_exec(
                ctx.compose_file or "",
                ctx.db_service,
                ctx.db_user,
                ctx.db_name,
                f"DELETE FROM security_events WHERE user_id IN ({user_list});",
            )
            executed.append("security_events_by_user")
        maybe_exec(
            "users",
            f"DELETE FROM users WHERE id IN ({user_list});",
            "users",
        )

    return {"mode": "hard", "executed": executed}


def cleanup(ctx: LoadContext, exam_ids: Sequence[int], user_ids: Sequence[int]) -> Dict[str, Any]:
    if ctx.cleanup_mode == "none":
        return {"mode": "none"}
    time.sleep(2.0)
    if ctx.cleanup_mode == "hard":
        try:
            return hard_cleanup(ctx, exam_ids, user_ids)
        except Exception as exc:
            fallback = {"hard_cleanup_error": str(exc)}
            fallback["api_fallback"] = api_cleanup(ctx, exam_ids, user_ids)
            return fallback
    return api_cleanup(ctx, exam_ids, user_ids)


def build_context(args: argparse.Namespace) -> LoadContext:
    report_dir = Path("reports") / f"{args.report_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    report_dir.mkdir(parents=True, exist_ok=True)
    session = new_session()
    admin_token, admin_user = resolve_admin_identity(args, session)
    system_settings = request_json(
        session,
        args.base_url,
        "GET",
        "/api/v1/settings/system",
        token=admin_token,
        expected=(200,),
        timeout=args.request_timeout,
    )
    minimum_apk_token, minimum_apk_token_source = resolve_minimum_apk_token(
        str(system_settings.get("minimum_apk_token") or "").strip()
    )
    if not minimum_apk_token:
        minimum_apk_token = FALLBACK_MINIMUM_APK_TOKEN
        minimum_apk_token_source = "fallback"
    original_allow_browser_testing = bool(system_settings.get("allow_browser_testing", False))
    browser_testing_toggled = False
    allowed_signatures_raw = str(system_settings.get("allowed_signatures") or "").strip()
    allow_mobile_apps = bool(system_settings.get("allow_mobile_apps", False))
    ensure_success(allow_mobile_apps, "allow_mobile_apps=false, load test siswa mobile tidak bisa dijalankan")
    allowed_signatures, app_signature_source = resolve_allowed_signatures(allowed_signatures_raw)
    if not allowed_signatures:
        # In environments where signatures are not configured yet, temporarily
        # enable browser testing (developer mode) so mobile-signature gate is bypassed.
        if not original_allow_browser_testing:
            update_browser_testing(
                session,
                args.base_url,
                admin_token,
                enabled=True,
                timeout=args.request_timeout,
            )
            browser_testing_toggled = True
        allowed_signatures = [FALLBACK_APP_SIGNATURE]
        app_signature_source = "fallback_developer_mode"

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    provision_workers = max(1, min(args.provision_workers, max(1, args.student_count)))
    strategy = args.provision_strategy
    if strategy == "auto":
        strategy = "batch" if args.student_count > 250 else "single"

    student_provision_results: List[ProvisionResult] = []
    successful_provision: List[ProvisionResult] = []

    if args.skip_provision:
        class_name = (args.reuse_student_class or "").strip().upper()
        teacher_username = (args.reuse_teacher_username or "").strip()
        teacher_password = (args.reuse_teacher_password or args.common_password or "").strip()
        ensure_success(bool(class_name), "--reuse-student-class wajib saat --skip-provision")
        ensure_success(bool(teacher_username), "--reuse-teacher-username wajib saat --skip-provision")
        ensure_success(bool(teacher_password), "password teacher kosong saat --skip-provision")
        teacher_token, teacher_user = login_user(
            args.base_url,
            teacher_username,
            teacher_password,
            args.request_timeout,
        )
        teacher = {
            "id": teacher_user["id"],
            "username": teacher_user["username"],
            "full_name": teacher_user.get("full_name") or teacher_username,
            "role": teacher_user.get("role") or "teacher",
        }
    else:
        teacher_username = f"{args.teacher_prefix}_{stamp}".lower()
        class_name = f"{args.class_prefix}_{stamp}".upper()
        teacher = create_teacher(session, args.base_url, admin_token, teacher_username, args.common_password, args.request_timeout)

        student_payloads = build_student_payloads(
            prefix=args.student_prefix.lower(),
            stamp=stamp,
            count=args.student_count,
            class_name=class_name,
            password=args.common_password,
        )
        if strategy == "batch":
            student_provision_results = provision_students_batch(
                session,
                args.base_url,
                admin_token,
                student_payloads,
                max(args.request_timeout, 60.0),
                batch_size=args.provision_batch_size,
            )
        else:
            max_provision_attempts = max(1, args.provision_retries + 1)
            pending_payloads = list(student_payloads)
            student_results_by_username: Dict[str, ProvisionResult] = {}
            for attempt in range(1, max_provision_attempts + 1):
                if not pending_payloads:
                    break
                attempt_results = provision_students(
                    args.base_url,
                    admin_token,
                    pending_payloads,
                    max(args.request_timeout, 60.0),
                    max_workers=min(provision_workers, max(1, len(pending_payloads))),
                )
                for item in attempt_results:
                    existing = student_results_by_username.get(item.username)
                    if item.ok:
                        student_results_by_username[item.username] = item
                        continue
                    if existing is None or not existing.ok:
                        student_results_by_username[item.username] = item
                pending_payloads = [
                    payload
                    for payload in pending_payloads
                    if not (student_results_by_username.get(str(payload["username"])) and student_results_by_username[str(payload["username"])].ok)
                ]
                if pending_payloads and attempt < max_provision_attempts:
                    time.sleep(max(0.1, args.provision_backoff_seconds * attempt))

            student_provision_results = sorted(
                student_results_by_username.values(),
                key=lambda item: item.username,
            )
        successful_provision = [item for item in student_provision_results if item.ok]
        teacher_token, _teacher_user = login_user(args.base_url, teacher_username, args.common_password, args.request_timeout)

    students_payload: Any
    if args.compose_file:
        students_payload = load_students_from_db(
            str(Path(args.compose_file)),
            args.db_service,
            args.db_user,
            args.db_name,
            class_name,
            limit=max(1000, args.student_count),
        )
    else:
        students_payload = request_json(
            session,
            args.base_url,
            "GET",
            f"/api/users?role=student&student_class={class_name}&limit={max(1000, args.student_count)}&sort_by=username&sort_order=asc",
            token=admin_token,
            expected=(200,),
            timeout=max(args.request_timeout, 120.0),
        )
    students = [
        Participant(user_id=int(item["id"]), username=str(item["username"]), full_name=str(item["full_name"]))
        for item in students_payload
        if str(item.get("student_class") or "").upper() == class_name
    ]
    if args.skip_provision:
        ensure_success(
            len(students) >= args.student_count,
            (
                f"student provisioning tidak lengkap: expected_min={args.student_count}, "
                f"verified={len(students)}, reported_success={len(successful_provision)}"
            ),
        )
        students = students[:args.student_count]
    else:
        ensure_success(
            len(students) == args.student_count,
            (
                f"student provisioning tidak lengkap: expected={args.student_count}, "
                f"verified={len(students)}, reported_success={len(successful_provision)}"
            ),
        )

    base_phase_sizes = parse_phase_sizes(args.phases, args.student_count)
    session_rounds = max(1, args.session_rounds)
    expanded_phase_sizes = base_phase_sizes * session_rounds

    raw_provision_success = len(successful_provision)
    raw_provision_failure = max(0, len(student_provision_results) - raw_provision_success)
    effective_provision_success = len(students) if not args.skip_provision else raw_provision_success
    effective_provision_failure = (
        max(0, args.student_count - len(students))
        if not args.skip_provision
        else 0
    )
    provision_reconciled = (
        not args.skip_provision
        and raw_provision_failure > 0
        and effective_provision_failure == 0
    )

    summary = {
        "created_at": utc_now().isoformat(),
        "base_url": args.base_url,
        "report_dir": str(report_dir.resolve()),
        "config": {
            "student_count": args.student_count,
            "skip_provision": bool(args.skip_provision),
            "reuse_student_class": class_name if args.skip_provision else "",
            "reuse_teacher_username": teacher_username if args.skip_provision else "",
            "phases": expanded_phase_sizes,
            "base_phases": base_phase_sizes,
            "session_rounds": session_rounds,
            "hold_seconds": args.hold_seconds,
            "start_timeout": args.start_timeout,
            "request_timeout": args.request_timeout,
            "cleanup_mode": args.cleanup_mode,
            "max_workers": args.max_workers,
            "provision_strategy": strategy,
            "provision_workers": provision_workers,
            "provision_retries": args.provision_retries,
            "provision_backoff_seconds": args.provision_backoff_seconds,
            "provision_batch_size": min(max(1, args.provision_batch_size), 500),
        },
        "artifacts": {},
        "provisioning": {
            "admin_user": {"id": admin_user["id"], "username": admin_user["username"]},
            "teacher": {"id": teacher["id"], "username": teacher["username"]},
            "student_class": class_name,
            "student_count": len(students),
            "minimum_apk_token": minimum_apk_token,
            "minimum_apk_token_source": minimum_apk_token_source,
            "app_signature_prefix": allowed_signatures[0][:12],
            "app_signature_source": app_signature_source,
            "browser_testing_toggled": browser_testing_toggled,
            "student_provision": {
                "success_count": effective_provision_success,
                "failure_count": effective_provision_failure,
                "raw_success_count": raw_provision_success,
                "raw_failure_count": raw_provision_failure,
                "verified_student_count": len(students),
                "reconciled_with_db_verification": provision_reconciled,
                "latency": summarize_latencies([item.latency_ms for item in student_provision_results]),
                "errors": [
                    {"username": item.username, "error": item.error}
                    for item in student_provision_results if not item.ok
                ][:50],
            },
        },
        "phases": [],
    }
    if args.skip_provision:
        summary["provisioning"]["student_provision"]["mode"] = "reused"
        summary["provisioning"]["student_provision"]["success_count"] = 0
        summary["provisioning"]["student_provision"]["failure_count"] = 0
        summary["provisioning"]["student_provision"]["latency"] = summarize_latencies([])
        summary["provisioning"]["student_provision"]["errors"] = []

    ctx = LoadContext(
        base_url=args.base_url,
        report_dir=report_dir,
        session=session,
        compose_file=str(Path(args.compose_file)) if args.compose_file else None,
        api_service=args.api_service,
        db_service=args.db_service,
        redis_service=args.redis_service,
        db_user=args.db_user,
        db_name=args.db_name,
        artifacts=summary["artifacts"],
        summary=summary,
        admin_token=admin_token,
        admin_user=admin_user,
        common_password=args.common_password,
        teacher=teacher,
        teacher_token=teacher_token,
        students=students,
        cleanup_mode=args.cleanup_mode,
        minimum_apk_token=minimum_apk_token,
        app_signature=allowed_signatures[0],
        original_allow_browser_testing=original_allow_browser_testing,
        browser_testing_toggled=browser_testing_toggled,
    )
    write_json(report_dir, ctx.artifacts, "provisioning.json", summary["provisioning"])
    write_json(
        report_dir,
        ctx.artifacts,
        "student_provision_results.json",
        [asdict(item) for item in student_provision_results],
    )
    return ctx


def restore_settings(ctx: LoadContext, timeout: float) -> None:
    if not ctx.browser_testing_toggled:
        return
    update_browser_testing(
        ctx.session,
        ctx.base_url,
        ctx.admin_token,
        enabled=ctx.original_allow_browser_testing,
        timeout=timeout,
    )


def main() -> int:
    args = parse_args()
    base_phase_sizes = parse_phase_sizes(args.phases, args.student_count)
    session_rounds = max(1, args.session_rounds)
    phase_sizes = base_phase_sizes * session_rounds
    ctx = build_context(args)
    exam_ids: List[int] = []
    managed_users = not bool((ctx.summary.get("config") or {}).get("skip_provision", False))
    user_ids = [int(ctx.teacher["id"])] + [item.user_id for item in ctx.students] if managed_users else []
    overall_pass = True

    try:
        for phase_index, phase_size in enumerate(phase_sizes, start=1):
            participants = ctx.students[:phase_size]
            phase = create_exam_phase(
                ctx,
                phase_size=phase_size,
                phase_index=phase_index,
                class_name=str(ctx.summary["provisioning"]["student_class"]),
                stamp=datetime.now().strftime("%H%M%S"),
                timeout=max(args.request_timeout, 120.0),
                created_exam_ids=exam_ids,
            )
            phase_report = run_exam_phase(
                ctx,
                phase,
                participants,
                phase_index=phase_index,
                timeout=args.request_timeout,
                start_timeout=args.start_timeout,
                hold_seconds=args.hold_seconds,
                max_workers=args.max_workers or phase_size,
                poll_jitter_seconds=args.poll_jitter_seconds,
            )
            ctx.summary["phases"].append(phase_report)
            overall_pass = overall_pass and bool(phase_report.get("pass"))

        ctx.summary["post_checks"] = {
            "health": request_json(
                ctx.session,
                ctx.base_url,
                "GET",
                "/health",
                expected=(200,),
                timeout=args.request_timeout,
            ),
            "final_logs": collect_phase_logs(
                ctx.compose_file,
                since=str(ctx.summary["created_at"]),
            ),
        }
        write_json(ctx.report_dir, ctx.artifacts, "final_logs.json", ctx.summary["post_checks"]["final_logs"])
        ctx.summary["pass"] = overall_pass
        return_code = 0 if overall_pass else 2
        return return_code
    finally:
        restore_error = None
        try:
            restore_settings(ctx, args.request_timeout)
            ctx.summary["settings_restored"] = True
        except Exception as exc:
            restore_error = str(exc)
            ctx.summary["settings_restored"] = False
            ctx.summary["settings_restore_error"] = restore_error

        cleanup_result = cleanup(ctx, exam_ids, user_ids)
        ctx.summary["cleanup"] = cleanup_result
        write_json(ctx.report_dir, ctx.artifacts, "summary.json", ctx.summary)
        print(json.dumps(ctx.summary, indent=2, ensure_ascii=False, default=str))
        ctx.session.close()


if __name__ == "__main__":
    raise SystemExit(main())
