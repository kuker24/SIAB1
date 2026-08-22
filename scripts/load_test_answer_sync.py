#!/usr/bin/env python3
"""Safe mobile-first answer-sync smoke/load helper.

This script is intentionally staging-first. By default it prints the planned
traffic only (--dry-run). To send traffic, pass --execute and provide staging
session/question IDs created for synthetic test data.

For realistic 300-600 concurrent evidence, use --sessions-csv so virtual users
are distributed across multiple synthetic sessions instead of contending on one
session lock.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

PRODUCTION_HOSTS = {"adminujian", "man1rokanhulu.cloud", "103.175.218.56"}
ANSWER_ENDPOINT = "/api/exams/submit-answer"
DEFAULT_FINAL_SUBMIT_ENDPOINT = "/api/student/exams/submit"
VIOLATION_ENDPOINT = "/api/exams/log-violation"


@dataclass(frozen=True)
class SessionRow:
    session_id: int
    question_id: int
    selected_option_id: int
    token: str = ""


@dataclass
class Sample:
    endpoint: str
    status_code: int
    latency_ms: float
    ok: bool


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * pct
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _status_counts(rows: Iterable[Sample]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for row in rows:
        counts[row.status_code] = counts.get(row.status_code, 0) + 1
    return dict(sorted(counts.items()))


def is_success_status(status_code: int) -> bool:
    """Return True only for HTTP 2xx load-test responses."""
    return 200 <= int(status_code) < 300


def summarize(samples: Iterable[Sample]) -> dict[str, object]:
    rows = list(samples)
    latencies = [row.latency_ms for row in rows]
    endpoint_names = sorted({row.endpoint for row in rows})
    per_endpoint: dict[str, dict[str, object]] = {}
    for endpoint in endpoint_names:
        endpoint_rows = [row for row in rows if row.endpoint == endpoint]
        endpoint_latencies = [row.latency_ms for row in endpoint_rows]
        per_endpoint[endpoint] = {
            "requests": len(endpoint_rows),
            "success": sum(1 for row in endpoint_rows if row.ok),
            "failures": sum(1 for row in endpoint_rows if not row.ok),
            "status_counts": _status_counts(endpoint_rows),
            "p50_ms": round(percentile(endpoint_latencies, 0.50), 2),
            "p95_ms": round(percentile(endpoint_latencies, 0.95), 2),
            "p99_ms": round(percentile(endpoint_latencies, 0.99), 2),
            "max_ms": round(max(endpoint_latencies), 2) if endpoint_latencies else 0.0,
        }

    return {
        "requests": len(rows),
        "success": sum(1 for row in rows if row.ok),
        "failures": sum(1 for row in rows if not row.ok),
        "status_counts": _status_counts(rows),
        "p50_ms": round(percentile(latencies, 0.50), 2),
        "p95_ms": round(percentile(latencies, 0.95), 2),
        "p99_ms": round(percentile(latencies, 0.99), 2),
        "max_ms": round(max(latencies), 2) if latencies else 0.0,
        "per_endpoint": per_endpoint,
    }


def build_summary(samples: Iterable[Sample], args: argparse.Namespace, rows: list[SessionRow]) -> dict[str, object]:
    summary = summarize(samples)
    summary.update(
        {
            "vus": int(args.vus),
            "duration_seconds": int(args.duration_seconds),
            "sessions_csv_used": bool(args.sessions_csv),
            "unique_sessions_count": len({row.session_id for row in rows}),
            "final_submit_sample_rate": float(args.final_submit_sample_rate),
            "final_submit_endpoint": str(args.final_submit_endpoint),
        }
    )
    return summary


def mask_token(token: str) -> str:
    value = str(token or "").strip()
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _parse_int(value: object, *, field_name: str, row_number: int) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Invalid {field_name} in CSV row {row_number}: {text!r}") from exc
    if parsed <= 0:
        raise SystemExit(f"Invalid {field_name} in CSV row {row_number}: must be positive")
    return parsed


def load_session_rows(
    csv_path: str | Path,
    fallback_token: str = "",
    fallback_selected_option_id: int = 1,
) -> list[SessionRow]:
    validate_sessions_csv_path(csv_path)
    path = Path(csv_path)
    if not path.exists():
        raise SystemExit(f"--sessions-csv not found: {path}")

    rows: list[SessionRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = {"session_id", "question_id"} - fieldnames
        if missing:
            raise SystemExit(
                "Invalid --sessions-csv: missing required column(s): "
                + ", ".join(sorted(missing))
            )

        for row_number, raw_row in enumerate(reader, start=2):
            session_id = _parse_int(raw_row.get("session_id"), field_name="session_id", row_number=row_number)
            question_id = _parse_int(raw_row.get("question_id"), field_name="question_id", row_number=row_number)
            if session_id is None or question_id is None:
                raise SystemExit(
                    f"Invalid --sessions-csv row {row_number}: session_id and question_id are required"
                )

            option_id = _parse_int(
                raw_row.get("selected_option_id"),
                field_name="selected_option_id",
                row_number=row_number,
            )
            if option_id is None:
                option_id = int(fallback_selected_option_id)
                if option_id <= 0:
                    raise SystemExit("--selected-option-id fallback must be positive")

            row_token = str(raw_row.get("token") or "").strip() or str(fallback_token or "").strip()
            rows.append(
                SessionRow(
                    session_id=session_id,
                    question_id=question_id,
                    selected_option_id=option_id,
                    token=row_token,
                )
            )

    if not rows:
        raise SystemExit("Invalid --sessions-csv: no session rows found")
    return rows


def assign_row(rows: list[SessionRow], worker_id: int) -> SessionRow:
    if not rows:
        raise ValueError("rows must not be empty")
    return rows[worker_id % len(rows)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Staging answer-sync load smoke/helper")
    parser.add_argument("--base-url", required=True, help="Staging base URL, e.g. https://staging.example.test")
    parser.add_argument("--token", default="", help="Bearer token fallback for staging test users")
    parser.add_argument("--session-id", type=int, default=None, help="Single-session smoke ExamSession ID")
    parser.add_argument("--question-id", type=int, default=None, help="Single-session smoke Question ID")
    parser.add_argument("--selected-option-id", type=int, default=1, help="Fallback option ID to submit")
    parser.add_argument("--sessions-csv", default="", help="CSV with session_id,question_id,selected_option_id,token")
    parser.add_argument("--vus", type=int, default=100, help="Virtual users/tasks to run")
    parser.add_argument("--duration-seconds", type=int, default=60, help="Duration for answer traffic")
    parser.add_argument("--think-ms-min", type=int, default=500, help="Minimum jitter between writes per VU")
    parser.add_argument("--think-ms-max", type=int, default=2500, help="Maximum jitter between writes per VU")
    parser.add_argument("--include-violation-burst", action="store_true", help="Send a light violation burst")
    parser.add_argument(
        "--final-submit-sample-rate",
        type=float,
        default=0.0,
        help="Experimental: fraction of workers that submit final-submit at the end (0.0-1.0)",
    )
    parser.add_argument(
        "--final-submit-endpoint",
        default=DEFAULT_FINAL_SUBMIT_ENDPOINT,
        help="Local path for final-submit sample; defaults to APK/student hot path",
    )
    parser.add_argument("--summary-json", default="", help="Write summary metrics JSON to this path; must be under /tmp")
    parser.add_argument("--answer-write-mode", default="direct", help="Safety declaration; Phase 4 requires direct")
    parser.add_argument("--answer-queue-enabled", default="false", help="Safety declaration; Phase 4 requires false")
    parser.add_argument("--answer-queue-percentage", type=int, default=0, help="Safety declaration; Phase 4 requires 0")
    parser.add_argument("--runtime-buffer-enabled", default="false", help="Safety declaration; Phase 4 requires false")
    parser.add_argument("--user-agent", default="load-test-answer-sync/1.0", help="User-Agent for load traffic")
    parser.add_argument("--seb-config-key-hash", default="", help="Optional SEB config key hash for staging synthetic exams")
    parser.add_argument("--execute", action="store_true", help="Actually send HTTP traffic. Default is dry-run.")
    return parser.parse_args()


def is_production_host(base_url: str) -> bool:
    parsed = urlparse(base_url)
    return (parsed.hostname or "").lower() in PRODUCTION_HOSTS


def _parse_boolish(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def is_safe_output_path(path_value: str | Path) -> bool:
    path = Path(path_value).expanduser()
    return path.is_absolute() and path.resolve().is_relative_to(Path("/tmp"))


def validate_sessions_csv_path(path_value: str | Path) -> None:
    if not is_safe_output_path(path_value):
        raise SystemExit("--sessions-csv must be an absolute path under /tmp to avoid committing tokens")


def validate_local_endpoint_path(endpoint: str, *, option_name: str) -> None:
    parsed = urlparse(str(endpoint or ""))
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        raise SystemExit(f"{option_name} must be a local absolute path such as /api/student/exams/submit")


def validate_direct_mode_policy(args: argparse.Namespace) -> None:
    answer_write_mode = str(getattr(args, "answer_write_mode", "direct") or "").strip().lower()
    queue_enabled = _parse_boolish(getattr(args, "answer_queue_enabled", False))
    queue_percentage = int(getattr(args, "answer_queue_percentage", 0) or 0)
    runtime_buffer_enabled = _parse_boolish(getattr(args, "runtime_buffer_enabled", False))

    if answer_write_mode != "direct":
        raise SystemExit("Phase 4 direct-mode validation requires --answer-write-mode=direct")
    if queue_enabled or queue_percentage != 0:
        raise SystemExit("Phase 4 direct-mode validation requires queue disabled and percentage 0")
    if runtime_buffer_enabled:
        raise SystemExit("Phase 4 direct-mode validation requires runtime buffer disabled")


def validate_args(args: argparse.Namespace, session_rows: Optional[list[SessionRow]] = None) -> None:
    parsed = urlparse(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit("--base-url must be an absolute http(s) URL")
    if is_production_host(args.base_url):
        raise SystemExit("Refusing production traffic; Phase 4 load tests must target local/staging only")
    validate_direct_mode_policy(args)
    validate_local_endpoint_path(args.final_submit_endpoint, option_name="--final-submit-endpoint")
    if args.sessions_csv:
        validate_sessions_csv_path(args.sessions_csv)
    if args.summary_json and not is_safe_output_path(args.summary_json):
        raise SystemExit("--summary-json must be an absolute path under /tmp to avoid committing artifacts")
    if args.vus <= 0 or args.duration_seconds <= 0:
        raise SystemExit("--vus and --duration-seconds must be positive")
    if args.think_ms_min < 0 or args.think_ms_max < args.think_ms_min:
        raise SystemExit("--think-ms-max must be >= --think-ms-min and both must be non-negative")
    if args.selected_option_id is not None and args.selected_option_id <= 0:
        raise SystemExit("--selected-option-id must be positive")
    if not 0.0 <= float(args.final_submit_sample_rate) <= 1.0:
        raise SystemExit("--final-submit-sample-rate must be between 0.0 and 1.0")
    if not args.sessions_csv and (args.session_id is None or args.question_id is None):
        raise SystemExit("--session-id and --question-id are required when --sessions-csv is not used")
    if args.session_id is not None and args.session_id <= 0:
        raise SystemExit("--session-id must be positive")
    if args.question_id is not None and args.question_id <= 0:
        raise SystemExit("--question-id must be positive")

    if args.execute:
        if session_rows is not None:
            missing_token_rows = [row.session_id for row in session_rows if not row.token]
            if missing_token_rows:
                raise SystemExit(
                    "--token is required when --execute is used unless every CSV row has a token"
                )
        elif not args.token:
            raise SystemExit("--token is required when --execute is used")


def build_session_rows(args: argparse.Namespace) -> list[SessionRow]:
    if args.sessions_csv:
        return load_session_rows(
            args.sessions_csv,
            fallback_token=args.token,
            fallback_selected_option_id=args.selected_option_id,
        )
    return [
        SessionRow(
            session_id=int(args.session_id),
            question_id=int(args.question_id),
            selected_option_id=int(args.selected_option_id),
            token=str(args.token or "").strip(),
        )
    ]


async def post_json(
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict[str, object],
    *,
    token: str,
) -> Sample:
    started = time.perf_counter()
    headers = dict(client.headers)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = await client.post(endpoint, json=payload, headers=headers)
        latency_ms = (time.perf_counter() - started) * 1000
        return Sample(
            endpoint=endpoint,
            status_code=response.status_code,
            latency_ms=latency_ms,
            ok=is_success_status(response.status_code),
        )
    except Exception:
        latency_ms = (time.perf_counter() - started) * 1000
        return Sample(endpoint=endpoint, status_code=0, latency_ms=latency_ms, ok=False)


async def answer_worker(
    client: httpx.AsyncClient,
    args: argparse.Namespace,
    rows: list[SessionRow],
    worker_id: int,
    stop_at: float,
    samples: list[Sample],
) -> None:
    session_row = assign_row(rows, worker_id)
    sequence = 0
    while time.perf_counter() < stop_at:
        sequence += 1
        payload = {
            "session_id": session_row.session_id,
            "question_id": session_row.question_id,
            "selected_option_id": session_row.selected_option_id,
            "client_sequence": f"load-{worker_id}-{sequence}",
        }
        samples.append(await post_json(client, ANSWER_ENDPOINT, payload, token=session_row.token))
        delay_ms = random.randint(args.think_ms_min, args.think_ms_max)
        await asyncio.sleep(delay_ms / 1000)


async def violation_burst(
    client: httpx.AsyncClient,
    args: argparse.Namespace,
    rows: list[SessionRow],
    samples: list[Sample],
) -> None:
    for burst_index in range(max(1, min(args.vus // 10, 50))):
        session_row = assign_row(rows, burst_index)
        payload = {
            "session_id": session_row.session_id,
            "exam_id": 0,
            "event_type": "focus_lost",
            "event_data": {"source": "load_test", "severity": "low"},
            "user_agent": "load-test-answer-sync/1.0",
            "screen_resolution": "test",
        }
        samples.append(await post_json(client, VIOLATION_ENDPOINT, payload, token=session_row.token))
        await asyncio.sleep(0.1)


def select_final_submit_rows(rows: list[SessionRow], vus: int, sample_rate: float) -> list[SessionRow]:
    if sample_rate <= 0:
        return []
    target_count = max(1, int(round(vus * sample_rate)))
    selected: list[SessionRow] = []
    seen_sessions: set[int] = set()
    for worker_id in range(vus):
        session_row = assign_row(rows, worker_id)
        if session_row.session_id in seen_sessions:
            continue
        selected.append(session_row)
        seen_sessions.add(session_row.session_id)
        if len(selected) >= target_count:
            break
    return selected


async def submit_final_samples(
    client: httpx.AsyncClient,
    args: argparse.Namespace,
    rows: list[SessionRow],
    samples: list[Sample],
) -> None:
    for session_row in select_final_submit_rows(rows, args.vus, args.final_submit_sample_rate):
        payload = {"session_id": session_row.session_id, "force_submit": False}
        samples.append(await post_json(client, args.final_submit_endpoint, payload, token=session_row.token))
        await asyncio.sleep(0.05)


async def run(args: argparse.Namespace, rows: list[SessionRow]) -> dict[str, object]:
    import httpx

    timeout = httpx.Timeout(connect=10, read=30, write=30, pool=30)
    limits = httpx.Limits(max_connections=max(10, args.vus), max_keepalive_connections=max(10, args.vus // 2))
    samples: list[Sample] = []
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": args.user_agent,
            **({"X-SafeExamBrowser-ConfigKeyHash": args.seb_config_key_hash} if args.seb_config_key_hash else {}),
        },
        timeout=timeout,
        limits=limits,
    ) as client:
        stop_at = time.perf_counter() + args.duration_seconds
        tasks = [answer_worker(client, args, rows, index, stop_at, samples) for index in range(args.vus)]
        if args.include_violation_burst:
            tasks.append(violation_burst(client, args, rows, samples))
        await asyncio.gather(*tasks)
        if args.final_submit_sample_rate > 0:
            await submit_final_samples(client, args, rows, samples)

    summary = build_summary(samples, args, rows)
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def print_plan(args: argparse.Namespace, rows: list[SessionRow]) -> None:
    print("Plan:")
    print(f"  base_url={args.base_url}")
    print(f"  vus={args.vus} duration_seconds={args.duration_seconds}")
    print(f"  sessions_csv_used={bool(args.sessions_csv)} unique_sessions={len({row.session_id for row in rows})}")
    print("  safety_policy=direct_mode queue_disabled runtime_buffer_disabled")
    print(f"  endpoint={ANSWER_ENDPOINT}")
    if args.seb_config_key_hash:
        print("  seb_config_key_hash=<provided>")
    if args.include_violation_burst:
        print(f"  endpoint={VIOLATION_ENDPOINT} (light burst)")
    if args.final_submit_sample_rate > 0:
        print(f"  endpoint={args.final_submit_endpoint} (experimental final-submit sample)")
        print(f"  final_submit_sample_rate={args.final_submit_sample_rate}")
    print(f"  first_token={mask_token(rows[0].token if rows else args.token)}")


def main() -> None:
    args = parse_args()
    rows = build_session_rows(args)
    validate_args(args, rows)
    print_plan(args, rows)
    if not args.execute:
        print("Dry-run only. Add --execute with staging token/session/question IDs to send traffic.")
        return
    summary = asyncio.run(run(args, rows))
    print("Answer sync load-smoke summary")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
