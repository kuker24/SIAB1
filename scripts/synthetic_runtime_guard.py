#!/usr/bin/env python3
"""
Synthetic runtime guard for exam-day monitoring.

Checks:
- HTTP success rate and p95 latency for selected endpoints
- Runtime telemetry snapshot thresholds (if admin token is provided)

Exit code:
- 0 => within configured thresholds
- 2 => threshold breached or hard failure
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class SampleResult:
    endpoint: str
    status: int
    latency_ms: float
    ok: bool
    error: Optional[str] = None


DEFAULT_ENDPOINTS = [
    "/health",
    "/api/monitoring/runtime-policy",
    "/api/monitoring/system/health",
    "/api/monitoring/system/runtime-metrics",
]


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = max(0.0, min(1.0, p)) * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return float(ordered[low])
    weight = rank - low
    return float(ordered[low] * (1.0 - weight) + ordered[high] * weight)


def build_request(url: str, token: Optional[str]) -> urllib.request.Request:
    headers = {
        "User-Agent": "synthetic-runtime-guard/1.0",
        "Accept": "application/json, text/plain, */*",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url=url, method="GET", headers=headers)


def call_endpoint(base_url: str, endpoint: str, token: Optional[str], timeout_sec: float) -> SampleResult:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))
    req = build_request(url, token)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            _ = resp.read(256)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            status = int(resp.getcode() or 0)
            return SampleResult(endpoint=endpoint, status=status, latency_ms=elapsed_ms, ok=200 <= status < 400)
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        status = int(exc.code or 0)
        return SampleResult(endpoint=endpoint, status=status, latency_ms=elapsed_ms, ok=False, error=str(exc))
    except Exception as exc:  # pragma: no cover
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return SampleResult(endpoint=endpoint, status=0, latency_ms=elapsed_ms, ok=False, error=str(exc))


def get_runtime_snapshot(base_url: str, token: str, timeout_sec: float) -> Dict:
    endpoint = "/api/monitoring/system/runtime-metrics"
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", endpoint.lstrip("/"))
    req = build_request(url, token)
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    data = json.loads(body)
    return data if isinstance(data, dict) else {}


def summarize(results: List[SampleResult]) -> Dict[str, Dict[str, float]]:
    by_endpoint: Dict[str, List[SampleResult]] = {}
    for item in results:
        by_endpoint.setdefault(item.endpoint, []).append(item)

    summary: Dict[str, Dict[str, float]] = {}
    for endpoint, samples in by_endpoint.items():
        latencies = [s.latency_ms for s in samples]
        ok_count = sum(1 for s in samples if s.ok)
        total = len(samples)
        summary[endpoint] = {
            "samples": float(total),
            "success_rate_percent": round((ok_count / total) * 100.0, 3) if total else 0.0,
            "latency_p50_ms": round(statistics.median(latencies), 2) if latencies else 0.0,
            "latency_p95_ms": round(percentile(latencies, 0.95), 2) if latencies else 0.0,
            "latency_max_ms": round(max(latencies), 2) if latencies else 0.0,
        }
    return summary


def evaluate_thresholds(
    endpoint_summary: Dict[str, Dict[str, float]],
    runtime_payload: Optional[Dict],
    max_error_percent: float,
    max_p95_ms: float,
) -> Tuple[bool, List[str]]:
    breaches: List[str] = []

    for endpoint, stats in endpoint_summary.items():
        success_rate = float(stats.get("success_rate_percent", 0.0))
        p95 = float(stats.get("latency_p95_ms", 0.0))
        error_rate = 100.0 - success_rate

        if error_rate > max_error_percent:
            breaches.append(
                f"{endpoint}: error_rate={error_rate:.2f}% > {max_error_percent:.2f}%"
            )
        if p95 > max_p95_ms:
            breaches.append(f"{endpoint}: p95={p95:.2f}ms > {max_p95_ms:.2f}ms")

    if runtime_payload:
        runtime = runtime_payload.get("runtime", {}) if isinstance(runtime_payload, dict) else {}
        global_error_rate = float(runtime.get("global", {}).get("error_rate_percent", 0.0))
        event_rates = runtime.get("event_rates_per_min", {}) if isinstance(runtime, dict) else {}
        db_pool_timeout = float(event_rates.get("db_pool_timeout", 0.0))
        redis_timeout = float(event_rates.get("redis_timeout", 0.0))

        if global_error_rate > max_error_percent:
            breaches.append(
                f"runtime.global.error_rate_percent={global_error_rate:.2f}% > {max_error_percent:.2f}%"
            )
        if db_pool_timeout > 1.0:
            breaches.append(f"runtime.event.db_pool_timeout={db_pool_timeout:.2f}/min > 1.00/min")
        if redis_timeout > 1.0:
            breaches.append(f"runtime.event.redis_timeout={redis_timeout:.2f}/min > 1.00/min")

    return (len(breaches) == 0, breaches)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic runtime guard checker")
    parser.add_argument("--base-url", default="http://127.0.0.1", help="Base URL target")
    parser.add_argument("--token", default=None, help="Bearer token (admin recommended)")
    parser.add_argument("--samples", type=int, default=10, help="Samples per endpoint")
    parser.add_argument("--sleep-ms", type=int, default=500, help="Pause between samples")
    parser.add_argument("--timeout-sec", type=float, default=8.0, help="HTTP timeout")
    parser.add_argument("--max-error-percent", type=float, default=3.0, help="Max error rate percent")
    parser.add_argument("--max-p95-ms", type=float, default=2000.0, help="Max p95 ms per endpoint")
    args = parser.parse_args()

    token = args.token
    endpoints = list(DEFAULT_ENDPOINTS)

    if not token:
        endpoints = ["/health"]

    print(f"[synthetic-runtime-guard] target={args.base_url} samples={args.samples} endpoints={endpoints}")
    all_results: List[SampleResult] = []

    for endpoint in endpoints:
        for _ in range(max(1, args.samples)):
            result = call_endpoint(args.base_url, endpoint, token, args.timeout_sec)
            all_results.append(result)
            time.sleep(max(0, args.sleep_ms) / 1000.0)

    endpoint_summary = summarize(all_results)

    runtime_payload: Optional[Dict] = None
    if token:
        try:
            runtime_payload = get_runtime_snapshot(args.base_url, token, args.timeout_sec)
        except Exception as exc:
            runtime_payload = {"fetch_error": str(exc)}

    ok, breaches = evaluate_thresholds(
        endpoint_summary=endpoint_summary,
        runtime_payload=runtime_payload if isinstance(runtime_payload, dict) else None,
        max_error_percent=args.max_error_percent,
        max_p95_ms=args.max_p95_ms,
    )

    output = {
        "target": args.base_url,
        "generated_at_unix": int(time.time()),
        "thresholds": {
            "max_error_percent": args.max_error_percent,
            "max_p95_ms": args.max_p95_ms,
        },
        "summary_by_endpoint": endpoint_summary,
        "runtime_snapshot": runtime_payload,
        "status": "PASS" if ok else "FAIL",
        "breaches": breaches,
    }

    print(json.dumps(output, indent=2))
    if ok:
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
