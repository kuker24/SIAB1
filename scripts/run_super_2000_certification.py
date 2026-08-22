#!/usr/bin/env python3
"""Run and certify 2000-user exam load profile in one command.

This wrapper keeps production execution repeatable:
- run `prod_concurrent_exam_load.py` with a super profile
- collect summary and apply explicit gate checks
- produce a compact certification report for go/no-go
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
LOAD_SCRIPT = REPO_ROOT / "scripts" / "prod_concurrent_exam_load.py"
REPORTS_DIR = REPO_ROOT / "reports"


@dataclass
class LatencyGate:
    metric: str
    threshold_ms: float
    observed_ms: Optional[float]
    passed: bool


@dataclass
class PhaseCertification:
    phase_index: int
    phase_size: int
    phase_pass: bool
    success_submit_count: int
    expected_submit_count: int
    latency_gates: List[LatencyGate]


@dataclass
class CertificationSummary:
    created_at: str
    profile: Dict[str, Any]
    load_test_return_code: int
    load_test_report_dir: Optional[str]
    load_test_pass: bool
    phases: List[PhaseCertification]
    hard_gates: Dict[str, bool]
    passed: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Super 2000-user certification wrapper")
    parser.add_argument("--base-url", default="http://127.0.0.1")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password", default="")
    parser.add_argument("--admin-token", default="")
    parser.add_argument("--bootstrap-admin-token-via-docker", action="store_true")
    parser.add_argument("--compose-file", default="docker-compose.production.yml")
    parser.add_argument("--api-service", default="api")
    parser.add_argument("--db-service", default="db")
    parser.add_argument("--redis-service", default="redis")
    parser.add_argument("--db-user", default="examuser")
    parser.add_argument("--db-name", default="exam_system")
    parser.add_argument("--teacher-prefix", default="loadtest_teacher")
    parser.add_argument("--student-prefix", default="loadtest_student")
    parser.add_argument("--class-prefix", default="LOAD2000")
    parser.add_argument("--common-password", default="LoadTemp#2026")

    parser.add_argument("--student-count", type=int, default=2000)
    parser.add_argument("--phases", default="500,1000,1500,2000")
    parser.add_argument("--session-rounds", type=int, default=1)
    parser.add_argument("--hold-seconds", type=float, default=12.0)
    parser.add_argument("--start-timeout", type=float, default=180.0)
    parser.add_argument("--request-timeout", type=float, default=90.0)
    parser.add_argument("--max-workers", type=int, default=0)

    parser.add_argument("--skip-provision", action="store_true")
    parser.add_argument("--reuse-student-class", default="")
    parser.add_argument("--reuse-teacher-username", default="")
    parser.add_argument("--reuse-teacher-password", default="")

    parser.add_argument(
        "--provision-strategy",
        choices=("auto", "batch", "single"),
        default="batch",
    )
    parser.add_argument("--provision-workers", type=int, default=24)
    parser.add_argument("--provision-retries", type=int, default=4)
    parser.add_argument("--provision-backoff-seconds", type=float, default=2.0)
    parser.add_argument("--provision-batch-size", type=int, default=500)

    parser.add_argument("--cleanup-mode", choices=("hard", "api", "none"), default="hard")
    parser.add_argument("--report-prefix", default="load_2000_super")

    # Certification thresholds. Set <= 0 to disable each gate.
    parser.add_argument("--max-p95-start-ms", type=float, default=30000.0)
    parser.add_argument("--max-p95-status-ms", type=float, default=12000.0)
    parser.add_argument("--max-p95-remaining-ms", type=float, default=12000.0)
    parser.add_argument("--max-p95-answer-ms", type=float, default=30000.0)
    parser.add_argument("--max-p95-submit-ms", type=float, default=20000.0)

    return parser.parse_args()


def _metric_observed(phase: Dict[str, Any], metric_name: str) -> Optional[float]:
    exam_flow = phase.get("exam_flow") or {}
    metric_payload = exam_flow.get(metric_name) or {}
    value = metric_payload.get("p95_ms")
    return float(value) if value is not None else None


def _apply_latency_gate(phase: Dict[str, Any], metric_name: str, threshold: float) -> LatencyGate:
    observed = _metric_observed(phase, metric_name)
    if threshold <= 0:
        return LatencyGate(
            metric=metric_name,
            threshold_ms=threshold,
            observed_ms=observed,
            passed=True,
        )
    passed = observed is not None and observed <= threshold
    return LatencyGate(
        metric=metric_name,
        threshold_ms=threshold,
        observed_ms=observed,
        passed=bool(passed),
    )


def _build_load_cmd(args: argparse.Namespace) -> List[str]:
    cmd = [
        sys.executable,
        str(LOAD_SCRIPT),
        "--base-url",
        args.base_url,
        "--admin-username",
        args.admin_username,
        "--compose-file",
        args.compose_file,
        "--api-service",
        args.api_service,
        "--db-service",
        args.db_service,
        "--redis-service",
        args.redis_service,
        "--db-user",
        args.db_user,
        "--db-name",
        args.db_name,
        "--teacher-prefix",
        args.teacher_prefix,
        "--student-prefix",
        args.student_prefix,
        "--class-prefix",
        args.class_prefix,
        "--common-password",
        args.common_password,
        "--student-count",
        str(args.student_count),
        "--phases",
        args.phases,
        "--session-rounds",
        str(args.session_rounds),
        "--hold-seconds",
        str(args.hold_seconds),
        "--start-timeout",
        str(args.start_timeout),
        "--request-timeout",
        str(args.request_timeout),
        "--provision-strategy",
        args.provision_strategy,
        "--provision-workers",
        str(args.provision_workers),
        "--provision-retries",
        str(args.provision_retries),
        "--provision-backoff-seconds",
        str(args.provision_backoff_seconds),
        "--provision-batch-size",
        str(args.provision_batch_size),
        "--cleanup-mode",
        args.cleanup_mode,
        "--report-prefix",
        args.report_prefix,
    ]

    if args.admin_password:
        cmd.extend(["--admin-password", args.admin_password])
    if args.admin_token:
        cmd.extend(["--admin-token", args.admin_token])
    if args.bootstrap_admin_token_via_docker:
        cmd.append("--bootstrap-admin-token-via-docker")
    if args.max_workers and args.max_workers > 0:
        cmd.extend(["--max-workers", str(args.max_workers)])

    if args.skip_provision:
        cmd.append("--skip-provision")
        if args.reuse_student_class:
            cmd.extend(["--reuse-student-class", args.reuse_student_class])
        if args.reuse_teacher_username:
            cmd.extend(["--reuse-teacher-username", args.reuse_teacher_username])
        if args.reuse_teacher_password:
            cmd.extend(["--reuse-teacher-password", args.reuse_teacher_password])

    return cmd


def _discover_new_report_dir(before: List[Path], prefix: str) -> Optional[Path]:
    after = [path for path in REPORTS_DIR.glob(f"{prefix}_*") if path.is_dir()]
    before_set = {path.resolve() for path in before}
    new_dirs = [path for path in after if path.resolve() not in before_set]
    if not new_dirs:
        return None
    new_dirs.sort(key=lambda path: path.stat().st_mtime)
    return new_dirs[-1]


def _load_summary(report_dir: Optional[Path]) -> Dict[str, Any]:
    if not report_dir:
        return {}
    summary_path = report_dir / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_phase_certifications(args: argparse.Namespace, summary: Dict[str, Any]) -> List[PhaseCertification]:
    phase_items = summary.get("phases") or []
    certifications: List[PhaseCertification] = []
    for index, phase in enumerate(phase_items, start=1):
        phase_size = int(phase.get("phase_size") or 0)
        exam_flow = phase.get("exam_flow") or {}
        success_submit_count = int(exam_flow.get("success_submit_count") or 0)

        latency_gates = [
            _apply_latency_gate(phase, "start_latency", args.max_p95_start_ms),
            _apply_latency_gate(phase, "status_latency", args.max_p95_status_ms),
            _apply_latency_gate(phase, "remaining_latency", args.max_p95_remaining_ms),
            _apply_latency_gate(phase, "answer_latency", args.max_p95_answer_ms),
            _apply_latency_gate(phase, "submit_latency", args.max_p95_submit_ms),
        ]

        phase_pass = bool(phase.get("pass", False))
        phase_pass = phase_pass and success_submit_count == phase_size
        phase_pass = phase_pass and all(gate.passed for gate in latency_gates)

        certifications.append(
            PhaseCertification(
                phase_index=index,
                phase_size=phase_size,
                phase_pass=phase_pass,
                success_submit_count=success_submit_count,
                expected_submit_count=phase_size,
                latency_gates=latency_gates,
            )
        )
    return certifications


def _write_certification_report(
    report_dir: Optional[Path],
    certification: CertificationSummary,
) -> None:
    if report_dir is None:
        return

    report_dir.mkdir(parents=True, exist_ok=True)

    json_path = report_dir / "super_2000_certification.json"
    md_path = report_dir / "super_2000_certification.md"

    json_payload = {
        **asdict(certification),
        "phases": [
            {
                **asdict(item),
                "latency_gates": [asdict(gate) for gate in item.latency_gates],
            }
            for item in certification.phases
        ],
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Super 2000 Certification")
    lines.append("")
    lines.append(f"- Created at: {certification.created_at}")
    lines.append(f"- Passed: {'YES' if certification.passed else 'NO'}")
    lines.append(f"- Load script RC: {certification.load_test_return_code}")
    lines.append(f"- Load summary pass: {certification.load_test_pass}")
    lines.append("")
    lines.append("## Phase Gates")
    lines.append("")

    for phase in certification.phases:
        lines.append(
            f"- Phase {phase.phase_index} ({phase.phase_size} users): "
            f"{'PASS' if phase.phase_pass else 'FAIL'} "
            f"submit={phase.success_submit_count}/{phase.expected_submit_count}"
        )
        for gate in phase.latency_gates:
            observed = "None" if gate.observed_ms is None else f"{gate.observed_ms:.2f}"
            lines.append(
                f"  - {gate.metric}: observed={observed}ms threshold={gate.threshold_ms:.2f}ms "
                f"=> {'PASS' if gate.passed else 'FAIL'}"
            )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    before_reports = [path for path in REPORTS_DIR.glob(f"{args.report_prefix}_*") if path.is_dir()]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    runner_log = REPORTS_DIR / f"{args.report_prefix}_runner_{timestamp}.log"

    cmd = _build_load_cmd(args)

    with runner_log.open("w", encoding="utf-8") as log_file:
        log_file.write("$ " + " ".join(cmd) + "\n")
        log_file.flush()
        process = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log_file.write(line)
        return_code = int(process.wait())
        log_file.write(f"\n[runner] rc={return_code}\n")

    report_dir = _discover_new_report_dir(before_reports, args.report_prefix)
    summary = _load_summary(report_dir)

    phase_certifications = _build_phase_certifications(args, summary)

    hard_gates = {
        "load_script_rc_zero": return_code == 0,
        "summary_pass_true": bool(summary.get("pass", False)),
        "all_phase_gates_pass": all(item.phase_pass for item in phase_certifications),
    }

    certification = CertificationSummary(
        created_at=datetime.now().isoformat(),
        profile={
            "student_count": args.student_count,
            "phases": args.phases,
            "session_rounds": args.session_rounds,
            "hold_seconds": args.hold_seconds,
            "start_timeout": args.start_timeout,
            "request_timeout": args.request_timeout,
            "cleanup_mode": args.cleanup_mode,
            "skip_provision": args.skip_provision,
            "reuse_student_class": args.reuse_student_class,
            "reuse_teacher_username": args.reuse_teacher_username,
        },
        load_test_return_code=return_code,
        load_test_report_dir=str(report_dir.resolve()) if report_dir else None,
        load_test_pass=bool(summary.get("pass", False)),
        phases=phase_certifications,
        hard_gates=hard_gates,
        passed=all(hard_gates.values()),
    )

    _write_certification_report(report_dir, certification)

    printable = {
        **asdict(certification),
        "phases": [
            {
                **asdict(item),
                "latency_gates": [asdict(gate) for gate in item.latency_gates],
            }
            for item in certification.phases
        ],
    }
    print(json.dumps(printable, indent=2, ensure_ascii=False))

    return 0 if certification.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
