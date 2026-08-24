from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_comprehensive_backup_is_private_and_checksummed() -> None:
    source = (ROOT / "bin" / "backup-comprehensive.sh").read_text(encoding="utf-8")

    assert "umask 077" in source
    assert "source .env" not in source
    assert 'if [ -s "$BACKUP_DIR/database/siab1.sql" ]' in source
    assert 'sha256sum "backup_${DATE}.tar.gz"' in source


def test_restore_drill_uses_latest_backup_and_temporary_database() -> None:
    source = (ROOT / "scripts" / "drill_disaster_recovery.sh").read_text(
        encoding="utf-8"
    )

    assert "sha256sum --check" in source
    assert "database/siab1.sql" in source
    assert 'DRILL_DB="drill_restore_${TIMESTAMP}"' in source
    assert "dropdb --if-exists" in source
    assert "DROP DATABASE siab1" not in source


def test_backup_installer_enables_daily_backup_and_weekly_drill() -> None:
    source = (ROOT / "scripts" / "install_backup_systemd.sh").read_text(
        encoding="utf-8"
    )

    assert "siab1-backup.timer" in source
    assert "siab1-restore-drill.timer" in source
    assert "Persistent=true" in source
    assert "UMask=0077" in source


def test_release_manifest_excludes_runtime_and_secret_material() -> None:
    source = (ROOT / "scripts" / "generate_release_manifest.sh").read_text(
        encoding="utf-8"
    )

    assert "docker/certs/*" in source
    assert "static/uploads/*" in source
    assert "static/apk/builds/*" in source
    assert "manifest_sha256=" in source
    assert "sha256sum --check" in source


def test_compose_defaults_to_host_controlled_restart_files() -> None:
    source = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")

    assert (
        "SYSTEM_FULL_RESTART_REQUEST_FILE=${SYSTEM_FULL_RESTART_REQUEST_FILE:-"
        "/app/runtime_control/system_full_restart.request.json}"
    ) in source
    assert (
        "SYSTEM_FULL_RESTART_STATUS_FILE=${SYSTEM_FULL_RESTART_STATUS_FILE:-"
        "/app/runtime_control/system_full_restart.status.json}"
    ) in source


def test_runtime_directory_setup_matches_container_uid() -> None:
    source = (ROOT / "scripts" / "prepare_runtime_dirs.sh").read_text(encoding="utf-8")

    assert 'APP_UID="${APP_UID:-1000}"' in source
    assert "static/uploads" in source
    assert "static/apk/builds" in source
    assert "static/seb/builds" in source
    assert 'chown -R "$APP_UID:$OPERATOR_GID" "$path"' in source
