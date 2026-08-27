from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "docs" / "operations" / "migration-history" / "archive"
MANIFEST = ROOT / "docs" / "operations" / "migration-history" / "CONTROL_MANIFEST.json"
SANITIZED_MIGRATION = (
    ROOT / "app" / "migrations" / "20260423_developer_role_and_seed_accounts.sql"
)
FINGERPRINT_SCRIPT = ROOT / "scripts" / "schema_fingerprint_readonly.py"

ARCHIVE_HASHES = {
    "20260312_partition_exam_logs_and_hot_indexes.sql.txt": (
        "abb39dddd7dd3bd258c9b5352a62c9acf5b83d887fa90e49f3dfd118f580942f"
    ),
    "20260313_exam_logs_partition_maintenance.sql.txt": (
        "bcbbaafd4f7418478784e6e08581664999e6b4c202d8f113b4ee1a20a9761ec1"
    ),
    "20260418_users_role_guruplus.sql.txt": (
        "2eb9307fcde1368ded7b7da0c0f0c87669098bf8f5d2e8915bbdb639a7af04c0"
    ),
    "create_materialized_views.sql.txt": (
        "52c436fac5e46c615eb4f814d6082e91ca81698c49cddc9556566b5f4f1dd1b6"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_archive_files_match_production_hashes() -> None:
    names = sorted(ARCHIVE_HASHES)
    assert sorted(path.name for path in ARCHIVE.glob("*.sql.txt")) == names
    for name, expected in ARCHIVE_HASHES.items():
        assert _sha256(ARCHIVE / name) == expected


def test_archive_files_are_inert_and_secret_free() -> None:
    for path in ARCHIVE.glob("*.sql.txt"):
        assert path.suffixes == [".sql", ".txt"]
        assert "app/migrations" not in path.as_posix()
        text = path.read_text(encoding="utf-8").lower()
        assert "password_hash" not in text
        assert "$2a$" not in text
        assert "$2b$" not in text
        assert "$2y$" not in text


def test_sanitized_developer_migration_has_no_credentials() -> None:
    source = SANITIZED_MIGRATION.read_text(encoding="utf-8")
    assert "INSERT INTO users" not in source
    assert "password_hash" not in source
    assert "$2a$" not in source
    assert "$2b$" not in source
    assert "$2y$" not in source


def test_fingerprint_script_is_read_only() -> None:
    source = FINGERPRINT_SCRIPT.read_text(encoding="utf-8")
    assert "SET TRANSACTION READ ONLY" in source
    assert "session.rollback()" in source
    assert "CREATE " not in source
    assert "ALTER " not in source
    assert "INSERT " not in source
    assert "UPDATE " not in source
    assert "DELETE " not in source


def test_control_manifest_exists_without_secrets() -> None:
    payload = MANIFEST.read_text(encoding="utf-8")
    assert "live-control-20260826-3f8fc938a226" in payload
    assert "password" not in payload.lower()
    assert "$2a$" not in payload
    assert "$2b$" not in payload
    assert "$2y$" not in payload
