import json
import sys
from pathlib import Path

import pytest

from scripts import analyze_answer_write_path as analyzer


DUMMY_SOURCE = """
async def hot_path(db):
    await db.execute("SELECT 1")
    await db.commit()
    query = query.with_for_update()
    await db.execute("SELECT pg_advisory_xact_lock(:namespace, :session_id)")
"""


def _make_repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    return root


def test_analyze_counts_hot_path_patterns_in_temp_repo(tmp_path, monkeypatch) -> None:
    root = _make_repo_root(tmp_path)
    dummy_path = root / "app" / "dummy_hot_path.py"
    dummy_path.write_text(DUMMY_SOURCE, encoding="utf-8")
    monkeypatch.setattr(
        analyzer,
        "HOT_PATH_FILES",
        {"dummy hot path": Path("app/dummy_hot_path.py")},
    )

    findings = analyzer.analyze(root)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.exists is True
    assert finding.counts["db_execute_calls"] == 2
    assert finding.counts["db_commits"] == 1
    assert finding.counts["row_locks"] == 1
    assert finding.counts["advisory_locks"] == 1


def test_analyzer_does_not_need_database_or_env(tmp_path, monkeypatch) -> None:
    root = _make_repo_root(tmp_path)
    (root / "app" / "dummy_hot_path.py").write_text(DUMMY_SOURCE, encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.setattr(
        analyzer,
        "HOT_PATH_FILES",
        {"dummy hot path": Path("app/dummy_hot_path.py")},
    )

    findings = analyzer.analyze(root)

    assert findings[0].exists is True
    assert findings[0].counts["db_execute_calls"] == 2


def test_validate_root_accepts_local_repo_like_root(tmp_path) -> None:
    root = _make_repo_root(tmp_path)

    analyzer._validate_root(root)


def test_validate_root_rejects_missing_app_or_scripts(tmp_path) -> None:
    missing_app = tmp_path / "missing-app"
    (missing_app / "scripts").mkdir(parents=True)
    with pytest.raises(SystemExit, match="Not a repository root"):
        analyzer._validate_root(missing_app)

    missing_scripts = tmp_path / "missing-scripts"
    (missing_scripts / "app").mkdir(parents=True)
    with pytest.raises(SystemExit, match="Not a repository root"):
        analyzer._validate_root(missing_scripts)


def test_main_json_outputs_valid_json_for_temp_repo(tmp_path, monkeypatch, capsys) -> None:
    root = _make_repo_root(tmp_path)
    (root / "app" / "dummy_hot_path.py").write_text(DUMMY_SOURCE, encoding="utf-8")
    monkeypatch.setattr(
        analyzer,
        "HOT_PATH_FILES",
        {"dummy hot path": Path("app/dummy_hot_path.py")},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze_answer_write_path.py",
            "--root",
            str(root),
            "--format",
            "json",
        ],
    )

    exit_code = analyzer.main()
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload[0]["label"] == "dummy hot path"
    assert payload[0]["counts"]["db_commits"] == 1


def test_analyzer_reads_only_configured_source_files(tmp_path, monkeypatch) -> None:
    root = _make_repo_root(tmp_path)
    sensitive_names = [
        ".env",
        "backup.dump",
        "answers.sql",
        "students.sqlite",
        "app-release.apk",
        "local.properties",
    ]
    for name in sensitive_names:
        (root / name).write_text("should-not-be-read", encoding="utf-8")

    read_paths = []

    def fake_read_source(_root: Path, relative_path: Path) -> str:
        read_paths.append(relative_path)
        return DUMMY_SOURCE

    monkeypatch.setattr(
        analyzer,
        "HOT_PATH_FILES",
        {"dummy hot path": Path("app/dummy_hot_path.py")},
    )
    monkeypatch.setattr(analyzer, "_read_source", fake_read_source)

    findings = analyzer.analyze(root)

    assert findings[0].exists is False or findings[0].label == "dummy hot path"
    assert read_paths == []

    (root / "app" / "dummy_hot_path.py").write_text(DUMMY_SOURCE, encoding="utf-8")
    findings = analyzer.analyze(root)

    assert findings[0].exists is True
    assert read_paths == [Path("app/dummy_hot_path.py")]
    assert all(path.name not in sensitive_names for path in read_paths)
