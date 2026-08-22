# Phase 29 Report - Bundle Registry Refactor

Date: 2026-03-07  
Environment: Local + VPS (`ujian-vps`)

## Scope

1. Replace manual bundle hash/build lists with one registry source of truth.
2. Refactor frontend bundle parity guard script to consume registry entries.
3. Refactor frontend parity pytest to consume the same registry entries.
4. Validate parity checks in local and VPS.

## Changes

- New registry:
  - `scripts/frontend_bundle_registry.csv`
- Refactored guard script:
  - `scripts/verify_frontend_bundles.sh`
- Refactored parity tests:
  - `tests/test_frontend_bundle_sync.py`

## Verification

- Local:
  - `bash scripts/verify_frontend_bundles.sh` -> `OK (28 bundles)`
  - `./.venv/bin/python -m pytest -q tests/test_frontend_bundle_sync.py` -> `28 passed`
- VPS:
  - `bash scripts/verify_frontend_bundles.sh` -> `OK (28 bundles)`
  - `python3 -m pytest -q tests/test_frontend_bundle_sync.py` unavailable (`pytest` not installed on host, and test path is not mounted inside API container)

## Outcome

Phase 29 completed with registry-driven bundle parity controls, removing repetitive manual updates and reducing drift risk for future phases.
