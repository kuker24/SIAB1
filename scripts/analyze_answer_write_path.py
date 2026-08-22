#!/usr/bin/env python3
"""Static direct-mode answer write-path review helper.

This helper intentionally does not connect to any database, does not read real
student data, and does not perform writes. It scans local source files for
high-concurrency hot-path signals so Phase 4 review can be repeated before
local/staging load tests.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

HOT_PATH_FILES = {
    "single/batch/journal answer sync": Path("app/services/answer_sync_service.py"),
    "answer sync route": Path("app/api/answer_sync.py"),
    "legacy answer sync route": Path("app/api/exam_answer_sync.py"),
    "final submit": Path("app/services/final_submit_service.py"),
    "violation events": Path("app/api/violation_events.py"),
    "admin monitoring": Path("app/api/monitoring.py"),
    "heavy exports": Path("app/api/exam_exports.py"),
}

PATTERNS = {
    "db_execute_calls": r"\.execute\(",
    "db_commits": r"\.commit\(",
    "db_rollbacks": r"\.rollback\(",
    "row_locks": r"with_for_update\(",
    "advisory_locks": r"pg_advisory_xact_lock",
    "exam_log_writes": r"ExamLog\(",
    "redis_session_markers": r"update_session_answers\(",
    "monitor_publish": r"publish_(?:message|monitoring_delta|exam_monitor_event)",
    "heavy_export_guard": r"heavy_exports_active|require_feature_enabled",
    "async_violation_guard": r"violation_async_enabled|enqueue_violation_event",
    "runtime_buffer_gate": r"is_runtime_answer_buffer_enabled",
    "queue_mode_gate": r"answer_write_mode|_answer_write_mode\(",
    "retry_after_503": r"Retry-After.*1|status_code=503",
}

PRODUCTION_URL_MARKERS = (
    "103.175.218.56",
    "man1rokanhulu.cloud",
    "adminujian",
)


@dataclass(frozen=True)
class FileFinding:
    label: str
    path: str
    exists: bool
    line_count: int
    counts: Dict[str, int]
    notes: List[str]


def _count_pattern(source: str, pattern: str) -> int:
    return len(re.findall(pattern, source, flags=re.IGNORECASE | re.MULTILINE))


def _read_source(root: Path, relative_path: Path) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _notes_for_counts(label: str, counts: Dict[str, int], source: str) -> List[str]:
    notes: List[str] = []
    if counts.get("db_commits", 0) > 0:
        notes.append("Contains explicit commit(s); check whether they are on student hot path.")
    if counts.get("row_locks", 0) or counts.get("advisory_locks", 0):
        notes.append("Uses session-level locking; correctness-safe but can serialize bursts.")
    if counts.get("exam_log_writes", 0) > 0:
        notes.append("Writes exam logs; ensure only critical logs remain in final-submit path.")
    if "violation" in label and counts.get("async_violation_guard", 0) > 0:
        notes.append("Violation path has async guard; keep enabled during peak.")
    if "monitor" in label and "summary" in source.lower():
        notes.append("Monitoring contains summary/aggregate-first indicators.")
    if counts.get("heavy_export_guard", 0) > 0:
        notes.append("Heavy export guard present; keep disabled during peak.")
    if counts.get("retry_after_503", 0) > 0:
        notes.append("Transient pressure can return 503 with Retry-After in this module.")
    return notes


def analyze(root: Path, labels: Iterable[str] | None = None) -> List[FileFinding]:
    selected_labels = set(labels or HOT_PATH_FILES.keys())
    findings: List[FileFinding] = []
    for label, relative_path in HOT_PATH_FILES.items():
        if label not in selected_labels:
            continue
        full_path = root / relative_path
        if not full_path.exists():
            findings.append(
                FileFinding(
                    label=label,
                    path=str(relative_path),
                    exists=False,
                    line_count=0,
                    counts={key: 0 for key in PATTERNS},
                    notes=["File not found."],
                )
            )
            continue
        source = _read_source(root, relative_path)
        counts = {key: _count_pattern(source, pattern) for key, pattern in PATTERNS.items()}
        findings.append(
            FileFinding(
                label=label,
                path=str(relative_path),
                exists=True,
                line_count=len(source.splitlines()),
                counts=counts,
                notes=_notes_for_counts(label, counts, source),
            )
        )
    return findings


def _validate_root(root: Path) -> None:
    root_text = str(root.resolve())
    if any(marker in root_text for marker in PRODUCTION_URL_MARKERS):
        raise SystemExit("Refusing production-like path/URL. Run this helper on a local checkout only.")
    if not (root / "app").is_dir() or not (root / "scripts").is_dir():
        raise SystemExit(f"Not a repository root: {root}")


def _print_text(findings: Sequence[FileFinding]) -> None:
    print("Phase 4 direct-mode static write-path review")
    print("Scope: local source only; no DB connection; no production data.\n")
    for finding in findings:
        print(f"## {finding.label} ({finding.path})")
        if not finding.exists:
            print("- missing\n")
            continue
        print(f"- lines: {finding.line_count}")
        for key, value in finding.counts.items():
            if value:
                print(f"- {key}: {value}")
        for note in finding.notes:
            print(f"- note: {note}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Static review helper for direct-mode answer/final-submit performance hot paths."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Local repository root. Must contain app/ and scripts/. Default: current directory.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. Default: text.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    _validate_root(root)
    findings = analyze(root)
    if args.format == "json":
        print(json.dumps([asdict(item) for item in findings], indent=2, ensure_ascii=False))
    else:
        _print_text(findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
