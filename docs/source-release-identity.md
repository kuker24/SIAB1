# Source Release Identity

Source release identity is not runtime filesystem identity.

- Source identity fingerprints Git-shaped production source and config.
- Runtime identity may include live canary maps, backups, logs, uploads, and host-only files.
- A delta file copy must never be labeled as a full-tree commit identity.

## Snapshot algorithm

Run the same command against a Git checkout or a staged deployment tree:

```bash
bash scripts/source_release_fingerprint.sh
```

Included roots: `app/`, `bin/`, `scripts/`, `templates/`, `docker/`, `monitoring/`,
`static/`, `go/`, `docker-compose.production.yml`, `requirements.txt`,
`requirements.runtime.txt`, `requirements.runtime.lock`, and `ARCHITECTURE.md`.

Excluded operational patterns include `.git/`, `.env*`, `logs/`, `uploads/`,
`recovery_sistem/`, generated `releases/` output, live `runtime_control/` state,
`docker/certs/*`, `static/uploads/*`, `static/apk/builds/*`, `static/seb/builds/*`,
`*.bak`, `*.bak-*`, `*.bak_*`, `*.pre-*`, `__pycache__/`, `.pytest_cache/`, and
`node_modules/`.

## Manifest modes

```bash
RELEASE_MODE=full bash scripts/generate_release_manifest.sh <git-sha>
RELEASE_MODE=delta DEPLOYED_PATHS_FILE=deployed.txt \
  SOURCE_GIT_SHA=<git-sha> bash scripts/generate_release_manifest.sh <release-id>
```

Full mode records the complete source fingerprint. Delta mode records only copied
files plus the source fingerprint of the tree they came from.

## 2026-08-28 production divergence

Inspected against `origin/main@72aa0107727309c528bf5be825b07fbe5a2b1eb0`:
57 divergences, 0 unexplained.

| Class | Count | Decision |
| --- | ---: | --- |
| VALID_PRODUCTION_SOURCE_CHANGE | 1 | Reconstructed `scripts/go_remaining_stage0.py` SEB headers into Git |
| INTENTIONAL_RUNTIME_DIFFERENCE | 20 | Keep Git FastAPI N=4/singleflight/telemetry and Git-only probes; do not copy older production control-plane Python |
| GENERATED_OR_OPERATIONAL_ARTIFACT | 13 | Exclude Nginx `.bak`/`.pre-*` files and generated JS bundles from source identity |
| STALE_OR_ACCIDENTAL_DRIFT | 23 | Line-ending or older restore script; Git remains canonical; do not reverse-copy |

Intentional Git-only control-plane files include `app/core/singleflight.py`,
`app/core/start_db_admission.py`, and `app/middleware/start_admission_bind.py`.
Live student routing remains Go 100% with FastAPI fallback.
