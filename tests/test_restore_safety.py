from pathlib import Path
import shlex
import subprocess


ROOT = Path(__file__).resolve().parents[1]
RESTORE_SOURCE = (ROOT / "bin" / "restore.sh").read_text(encoding="utf-8")


def test_restore_script_can_be_sourced_without_running_interactive_main() -> None:
    assert 'if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then' in RESTORE_SOURCE


def run_bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_file_copy_failure_keeps_existing_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    restore_dir = tmp_path / "restore"
    (workspace / "uploads").mkdir(parents=True)
    (workspace / "uploads" / "existing.txt").write_text("existing", encoding="utf-8")
    (restore_dir / "uploads").mkdir(parents=True)
    (restore_dir / "uploads" / "replacement.txt").write_text("replacement", encoding="utf-8")

    result = run_bash(
        f"""
        source {shlex.quote(str(ROOT / 'bin' / 'restore.sh'))}
        PROJECT_ROOT={shlex.quote(str(workspace))}
        RESTORE_DIR={shlex.quote(str(restore_dir))}
        cd "$PROJECT_ROOT"
        cp() {{ return 1; }}
        if restore_files; then exit 10; fi
        test -f uploads/existing.txt
        test ! -e uploads/replacement.txt
        """
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_database_restore_is_strict_and_staged(tmp_path: Path) -> None:
    restore_dir = tmp_path / "restore"
    (restore_dir / "database").mkdir(parents=True)
    (restore_dir / "database" / "siab1.sql").write_text("SELECT 1;", encoding="utf-8")
    call_log = tmp_path / "compose-calls.log"

    result = run_bash(
        f"""
        source {shlex.quote(str(ROOT / 'bin' / 'restore.sh'))}
        RESTORE_DIR={shlex.quote(str(restore_dir))}
        CALL_LOG={shlex.quote(str(call_log))}
        DC=mock_compose
        sleep() {{ :; }}
        mock_compose() {{
            printf '%s\n' "$*" >> "$CALL_LOG"
            if [[ "$*" == *"information_schema.tables"* ]]; then
                printf '5\n'
            fi
            return 0
        }}
        restore_database
        grep -q -- '-v ON_ERROR_STOP=1' "$CALL_LOG"
        grep -q -- '--single-transaction' "$CALL_LOG"
        grep -q -- 'siab1_restore_staging' "$CALL_LOG"
        """
    )

    assert result.returncode == 0, result.stderr + result.stdout


def test_failed_verification_rolls_back_and_returns_failure(tmp_path: Path) -> None:
    rollback_marker = tmp_path / "rolled-back"

    result = run_bash(
        f"""
        source {shlex.quote(str(ROOT / 'bin' / 'restore.sh'))}
        create_safety_backup() {{ :; }}
        stop_services() {{ :; }}
        extract_backup() {{ :; }}
        restore_database() {{ :; }}
        restore_files() {{ :; }}
        start_services() {{ :; }}
        verify_system() {{ return 1; }}
        rollback_restore() {{ touch {shlex.quote(str(rollback_marker))}; }}
        cleanup() {{ :; }}
        if run_restore unused-backup; then exit 20; fi
        test -f {shlex.quote(str(rollback_marker))}
        """
    )

    assert result.returncode == 0, result.stderr + result.stdout
