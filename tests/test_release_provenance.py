from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        env=merged,
        check=True,
        text=True,
        capture_output=True,
    )


def test_source_fingerprint_is_deterministic_and_excludes_operational_artifacts() -> None:
    first = _run(["bash", "scripts/source_release_fingerprint.sh"]).stdout
    second = _run(["bash", "scripts/source_release_fingerprint.sh"]).stdout
    assert first == second
    assert first.strip()
    paths = [line.split("  ", 1)[1] for line in first.splitlines()]
    joined = "\n".join(paths)
    assert "docker/certs/" not in joined
    assert "static/uploads/" not in joined
    assert "runtime_control/" not in joined
    assert ".env" not in joined
    assert not any(path.endswith(".bak") or ".bak-" in path or ".bak_" in path for path in paths)
    assert not any(".pre-" in path for path in paths)
    assert "app/main.py" in paths
    assert "go/cmd/server/main.go" in paths
    assert "docker-compose.production.yml" in paths


def test_full_manifest_records_source_identity_fields(tmp_path: Path) -> None:
    output = tmp_path / "releases"
    result = _run(
        ["bash", "scripts/generate_release_manifest.sh", "test-full"],
        env={
            "OUTPUT_DIR": str(output),
            "RELEASE_MODE": "full",
            "SOURCE_GIT_SHA": "72aa0107727309c528bf5be825b07fbe5a2b1eb0",
            "SOURCE_BRANCH": "ops/production-source-reconciliation",
            "DEPLOYMENT_DESTINATION": "/opt/siab1",
            "PREVIOUS_RELEASE_ID": "1a2214c",
            "PREVIOUS_SOURCE_SHA": "7da0993f6001ca311c84cea380094f2be009e1dd",
            "BACKUP_PATH": "/opt/siab1/recovery_sistem/backup_example.tar.gz",
            "BACKUP_SHA256": "abc123",
        },
    )
    metadata = (output / "release-test-full.metadata").read_text(encoding="utf-8")
    listing = (output / "release-test-full.source-tree.sha256").read_text(encoding="utf-8")
    manifest = output / "release-test-full.sha256"
    assert "release_mode=full" in metadata
    assert "source_git_sha=72aa0107727309c528bf5be825b07fbe5a2b1eb0" in metadata
    assert "source_tree_fingerprint=" in metadata
    assert "compose_file_identity=" in metadata
    assert "nginx_config_identity=" in metadata
    assert "identity_note=source_release_identity_is_not_runtime_filesystem_identity" in metadata
    assert "docker/certs/*" in metadata
    assert listing == manifest.read_text(encoding="utf-8")
    assert "sha256sum --check" in result.stdout
    _run(["sha256sum", "--check", "--status", str(manifest)])


def test_delta_manifest_does_not_claim_full_tree_identity(tmp_path: Path) -> None:
    deployed = tmp_path / "deployed.txt"
    deployed.write_text("scripts/go_remaining_stage0.py\nARCHITECTURE.md\n", encoding="utf-8")
    output = tmp_path / "releases"
    _run(
        ["bash", "scripts/generate_release_manifest.sh", "test-delta"],
        env={
            "OUTPUT_DIR": str(output),
            "RELEASE_MODE": "delta",
            "DEPLOYED_PATHS_FILE": str(deployed),
            "SOURCE_GIT_SHA": "72aa0107727309c528bf5be825b07fbe5a2b1eb0",
        },
    )
    metadata = (output / "release-test-delta.metadata").read_text(encoding="utf-8")
    manifest = (output / "release-test-delta.sha256").read_text(encoding="utf-8")
    source_listing = (output / "release-test-delta.source-tree.sha256").read_text(encoding="utf-8")
    assert "release_mode=delta" in metadata
    assert "scripts/go_remaining_stage0.py" in manifest
    assert "ARCHITECTURE.md" in manifest
    assert "app/main.py" not in manifest
    assert "app/main.py" in source_listing
    assert manifest != source_listing


def test_future_images_declare_oci_provenance_labels() -> None:
    production = (ROOT / "docker" / "Dockerfile.production").read_text(encoding="utf-8")
    go_file = (ROOT / "docker" / "Dockerfile.go").read_text(encoding="utf-8")
    pgbouncer = (ROOT / "docker" / "Dockerfile.pgbouncer").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    for source in (production, go_file, pgbouncer):
        assert "org.opencontainers.image.revision=" in source
        assert "org.opencontainers.image.source=" in source
        assert "org.opencontainers.image.version=" in source
        assert "org.opencontainers.image.created=" in source
    assert "x-oci-build-args:" in compose
    assert "Nginx tetap ke Python sampai parity" not in compose


def test_architecture_records_hybrid_go_fastapi_production() -> None:
    source = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "hybrid modular monolith" in source
    assert "bukan arsitektur microservices" in source
    assert "Go adalah student hot-path data plane" in source
    assert "bukan tanda bahwa Go masih eksperimental" in source


def test_fingerprint_and_manifest_scripts_are_private_mode() -> None:
    for relative in (
        "scripts/source_release_fingerprint.sh",
        "scripts/generate_release_manifest.sh",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "umask 077" in source
