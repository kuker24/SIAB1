# Phase 11 Report - Sidebar Loader Modularization + Guard Expansion

Date: 2026-03-06  
Environment: Local + VPS (`ujian-vps`)

## Scope

1. Split `static/js/sidebar-loader.js` into modular sources.
2. Add deterministic bundle builder for sidebar loader bundle.
3. Expand bundle sync guard and parity tests to include sidebar loader.
4. Validate end-to-end on local and VPS.

## Changes

- New module sources:
  - `static/js/sidebar-loader/modules/00-sidebar-loader-core.js`
  - `static/js/sidebar-loader/modules/10-sidebar-loader-bootstrap.js`
- New builder script:
  - `scripts/build_sidebar_loader_bundle.sh`
- Generated bundle:
  - `static/js/sidebar-loader.js`
- Guard/test extension:
  - `scripts/verify_frontend_bundles.sh`
  - `tests/test_frontend_bundle_sync.py`
- Behavior parity fix:
  - Restore fallback menu visibility rule for `violations` to `admin-only`.

## Verification

- Local:
  - `scripts/build_sidebar_loader_bundle.sh`
  - `scripts/verify_frontend_bundles.sh`
  - `node --check static/js/sidebar-loader.js`
  - `./.venv/bin/python -m pytest -q tests/test_frontend_bundle_sync.py` -> `11 passed`
- VPS:
  - `bash scripts/verify_frontend_bundles.sh`
  - `node --check static/js/sidebar-loader.js`
  - `bash scripts/verify_stable_release_vps.sh` -> `PASS`

## Outcome

Phase 11 completed with modular source control for sidebar loading flow and stronger automated sync checks on both local and VPS.
