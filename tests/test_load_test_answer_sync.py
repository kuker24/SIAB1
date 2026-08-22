from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path

import pytest


SCRIPT_PATH = Path("scripts/load_test_answer_sync.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("load_test_answer_sync", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules["load_test_answer_sync"] = module
    spec.loader.exec_module(module)
    return module


load_script = _load_module()


def _args(**overrides):
    values = {
        "base_url": "https://staging.example.test",
        "token": "",
        "session_id": 1001,
        "question_id": 2001,
        "selected_option_id": 3001,
        "sessions_csv": "",
        "vus": 10,
        "duration_seconds": 60,
        "think_ms_min": 500,
        "think_ms_max": 2500,
        "include_violation_burst": False,
        "final_submit_sample_rate": 0.0,
        "final_submit_endpoint": load_script.DEFAULT_FINAL_SUBMIT_ENDPOINT,
        "summary_json": "",
        "answer_write_mode": "direct",
        "answer_queue_enabled": "false",
        "answer_queue_percentage": 0,
        "runtime_buffer_enabled": "false",
        "execute": False,
    }
    values.update(overrides)
    return Namespace(**values)


def test_validate_args_rejects_production_host() -> None:
    with pytest.raises(SystemExit, match="Refusing production traffic"):
        load_script.validate_args(_args(base_url="https://man1rokanhulu.cloud"))


@pytest.mark.parametrize(
    "base_url",
    ["https://man1rokanhulu.cloud", "http://103.175.218.56", "https://adminujian"],
)
def test_validate_args_rejects_known_production_like_hosts(base_url) -> None:
    with pytest.raises(SystemExit, match="Refusing production traffic"):
        load_script.validate_args(_args(base_url=base_url))


def test_old_allow_production_flag_is_not_supported(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "load_test_answer_sync.py",
            "--base-url",
            "https://man1rokanhulu.cloud",
            "--session-id",
            "1001",
            "--question-id",
            "2001",
            "--allow-production",
        ],
    )

    with pytest.raises(SystemExit):
        load_script.parse_args()


def test_dry_run_default_does_not_execute_http(monkeypatch, capsys) -> None:
    async def fail_run(*_args, **_kwargs):
        raise AssertionError("run() must not be called during dry-run")

    monkeypatch.setattr(load_script, "run", fail_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "load_test_answer_sync.py",
            "--base-url",
            "https://staging.example.test",
            "--session-id",
            "1001",
            "--question-id",
            "2001",
        ],
    )

    load_script.main()

    output = capsys.readouterr().out
    assert "Dry-run only" in output
    assert "endpoint=/api/exams/submit-answer" in output
    assert "safety_policy=direct_mode queue_disabled runtime_buffer_disabled" in output


def test_csv_parser_reads_session_question_option_and_token(tmp_path) -> None:
    csv_file = tmp_path / "sessions.csv"
    csv_file.write_text(
        "session_id,question_id,selected_option_id,token\n"
        "1001,2001,3001,token-one\n"
        "1002,2002,,\n",
        encoding="utf-8",
    )

    rows = load_script.load_session_rows(
        csv_file,
        fallback_token="fallback-token",
        fallback_selected_option_id=9999,
    )

    assert rows == [
        load_script.SessionRow(1001, 2001, 3001, "token-one"),
        load_script.SessionRow(1002, 2002, 9999, "fallback-token"),
    ]


def test_execute_with_csv_requires_token_for_every_row(tmp_path) -> None:
    csv_file = tmp_path / "sessions.csv"
    csv_file.write_text(
        "session_id,question_id,selected_option_id,token\n"
        "1001,2001,3001,\n",
        encoding="utf-8",
    )
    rows = load_script.load_session_rows(csv_file, fallback_token="", fallback_selected_option_id=1)

    with pytest.raises(SystemExit, match="--token is required"):
        load_script.validate_args(_args(sessions_csv=str(csv_file), execute=True), rows)


def test_execute_with_csv_allows_per_row_tokens_without_global_token(tmp_path) -> None:
    csv_file = tmp_path / "sessions.csv"
    csv_file.write_text(
        "session_id,question_id,selected_option_id,token\n"
        "1001,2001,3001,row-token\n",
        encoding="utf-8",
    )
    rows = load_script.load_session_rows(csv_file, fallback_token="", fallback_selected_option_id=1)

    load_script.validate_args(_args(sessions_csv=str(csv_file), execute=True), rows)


def test_default_final_submit_endpoint_targets_student_apk_hot_path() -> None:
    assert load_script.DEFAULT_FINAL_SUBMIT_ENDPOINT == "/api/student/exams/submit"
    args = _args(final_submit_sample_rate=0.1)

    load_script.validate_args(args)

    samples = [load_script.Sample(args.final_submit_endpoint, 200, 10.0, True)]
    summary = load_script.build_summary(samples, args, [load_script.SessionRow(1001, 2001, 3001, "secret")])
    assert summary["final_submit_endpoint"] == "/api/student/exams/submit"
    assert "secret" not in str(summary)


@pytest.mark.parametrize("endpoint", ["/api/student/exams/submit", "/api/exams/submit"])
def test_custom_final_submit_endpoint_accepts_local_absolute_path(endpoint) -> None:
    load_script.validate_args(_args(final_submit_endpoint=endpoint))


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://man1rokanhulu.cloud/api/student/exams/submit",
        "http://103.175.218.56/api/student/exams/submit",
        "api/student/exams/submit",
        "//man1rokanhulu.cloud/api/student/exams/submit",
    ],
)
def test_invalid_final_submit_endpoint_rejected(endpoint) -> None:
    with pytest.raises(SystemExit, match="--final-submit-endpoint must be a local absolute path"):
        load_script.validate_args(_args(final_submit_endpoint=endpoint))


def test_sessions_csv_must_be_under_tmp() -> None:
    load_script.validate_args(_args(sessions_csv="/tmp/ujianonline-direct-sessions.csv"))
    load_script.validate_args(_args(sessions_csv="/tmp/subdir/sessions.csv"))

    for invalid_path in ["docs/sessions.csv", "sessions.csv", "/home/user/repo/sessions.csv"]:
        with pytest.raises(SystemExit, match="--sessions-csv must be an absolute path under /tmp"):
            load_script.validate_args(_args(sessions_csv=invalid_path))


def test_load_session_rows_rejects_non_tmp_csv_before_reading() -> None:
    with pytest.raises(SystemExit, match="--sessions-csv must be an absolute path under /tmp"):
        load_script.load_session_rows("docs/sessions.csv")


def test_summary_json_must_be_under_tmp() -> None:
    load_script.validate_args(_args(summary_json="/tmp/ujianonline-load-summary.json"))

    for invalid_path in ["docs/summary.json", "summary.json"]:
        with pytest.raises(SystemExit, match="--summary-json must be an absolute path under /tmp"):
            load_script.validate_args(_args(summary_json=invalid_path))


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"answer_write_mode": "hybrid"}, "requires --answer-write-mode=direct"),
        ({"answer_queue_enabled": "true"}, "requires queue disabled"),
        ({"answer_queue_percentage": 10}, "requires queue disabled"),
        ({"runtime_buffer_enabled": "true"}, "requires runtime buffer disabled"),
    ],
)
def test_direct_mode_policy_rejects_hybrid_queue_or_runtime_buffer(overrides, expected) -> None:
    with pytest.raises(SystemExit, match=expected):
        load_script.validate_args(_args(**overrides))


def test_dry_run_masks_full_token(monkeypatch, capsys) -> None:
    token = "abcdefghijklmnopqrstuvwxyz"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "load_test_answer_sync.py",
            "--base-url",
            "https://staging.example.test",
            "--session-id",
            "1001",
            "--question-id",
            "2001",
            "--token",
            token,
        ],
    )

    load_script.main()

    output = capsys.readouterr().out
    assert token not in output
    assert "abcd...wxyz" in output


def test_mask_token_does_not_print_full_secret() -> None:
    token = "abcdefghijklmnopqrstuvwxyz"
    masked = load_script.mask_token(token)

    assert masked == "abcd...wxyz"
    assert token not in masked
    assert load_script.mask_token("") == "<empty>"
    assert load_script.mask_token("short") == "****"


def test_round_robin_worker_assignment_is_stable() -> None:
    rows = [
        load_script.SessionRow(1001, 2001, 3001, "t1"),
        load_script.SessionRow(1002, 2002, 3002, "t2"),
        load_script.SessionRow(1003, 2003, 3003, "t3"),
    ]

    assigned_sessions = [load_script.assign_row(rows, worker_id).session_id for worker_id in range(7)]

    assert assigned_sessions == [1001, 1002, 1003, 1001, 1002, 1003, 1001]


def test_success_status_counts_only_2xx() -> None:
    success_codes = [200, 201, 202, 204, 299]
    failure_codes = [0, 300, 400, 401, 403, 404, 429, 500, 503]

    for status_code in success_codes:
        assert load_script.is_success_status(status_code) is True
    for status_code in failure_codes:
        assert load_script.is_success_status(status_code) is False


def test_summarize_counts_4xx_as_failure() -> None:
    samples = [
        load_script.Sample(
            "/api/exams/submit-answer",
            200,
            10.0,
            load_script.is_success_status(200),
        ),
        load_script.Sample(
            "/api/exams/submit-answer",
            429,
            20.0,
            load_script.is_success_status(429),
        ),
        load_script.Sample(
            "/api/exams/submit-answer",
            401,
            30.0,
            load_script.is_success_status(401),
        ),
    ]

    summary = load_script.summarize(samples)
    per_endpoint = summary["per_endpoint"]["/api/exams/submit-answer"]

    assert summary["requests"] == 3
    assert summary["success"] == 1
    assert summary["failures"] == 2
    assert summary["status_counts"] == {200: 1, 401: 1, 429: 1}
    assert per_endpoint["success"] == 1
    assert per_endpoint["failures"] == 2
    assert per_endpoint["status_counts"] == {200: 1, 401: 1, 429: 1}


def test_summarize_includes_percentiles_and_per_endpoint() -> None:
    samples = [
        load_script.Sample("/api/exams/submit-answer", 200, 10.0, True),
        load_script.Sample("/api/exams/submit-answer", 200, 20.0, True),
        load_script.Sample("/api/exams/submit", 503, 30.0, False),
    ]

    summary = load_script.summarize(samples)

    assert summary["requests"] == 3
    assert summary["success"] == 2
    assert summary["failures"] == 1
    assert summary["p50_ms"] == 20.0
    assert summary["p95_ms"] > 0
    assert summary["p99_ms"] > 0
    assert "/api/exams/submit-answer" in summary["per_endpoint"]
    assert summary["per_endpoint"]["/api/exams/submit"]["status_counts"] == {503: 1}


@pytest.mark.parametrize(
    "csv_text,expected",
    [
        ("question_id,selected_option_id,token\n2001,3001,t\n", "missing required column"),
        ("session_id,selected_option_id,token\n1001,3001,t\n", "missing required column"),
        ("session_id,question_id,selected_option_id,token\n,2001,3001,t\n", "session_id and question_id are required"),
    ],
)
def test_invalid_csv_missing_required_session_or_question_fails(tmp_path, csv_text, expected) -> None:
    csv_file = tmp_path / "invalid.csv"
    csv_file.write_text(csv_text, encoding="utf-8")

    with pytest.raises(SystemExit, match=expected):
        load_script.load_session_rows(csv_file, fallback_token="fallback", fallback_selected_option_id=1)
