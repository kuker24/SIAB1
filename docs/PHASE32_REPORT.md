# Phase 32 Report - Security Hardening and Regression Closure

Date: 2026-03-07  
Environment: Local + VPS (`ujian-vps`)

## Scope

1. Add mitigation for expensive HTTP `Range` parsing abuse on file responses.
2. Stabilize vulnerability scanner behavior for empty/missing fix-version payloads.
3. Complete regression verification after hardening changes.

## Changes

- Range header guard middleware:
  - `app/middleware/security.py`
  - Added `_SIMPLE_BYTE_RANGE_RE`
  - Added `RangeHeaderGuardMiddleware` to strip malformed/multi-range headers.
- Middleware registration:
  - `app/main.py`
  - Registered `RangeHeaderGuardMiddleware` before `SecurityHeadersMiddleware`.
- Dependency hardening:
  - `requirements.txt`
  - Upgraded `python-multipart` to `0.0.22`.
- Security scanner robustness fix:
  - `scripts/check_security.py`
  - Scan now reports only packages with `vulns`.
  - Added safe fallback when `fix_versions` is empty.
- Test coverage:
  - `tests/test_range_header_guard.py`
  - Added source-level checks for middleware existence and registration order.

## Verification

- Local:
  - `./.venv/bin/python -m pytest -q tests/test_range_header_guard.py` -> `2 passed`
  - `./.venv/bin/python -m pytest -q tests` -> `97 passed`
  - `./.venv/bin/python -m compileall app` -> `OK`
  - `./.venv/bin/python scripts/check_security.py` -> scanner completed, exits non-zero only for unresolved external CVEs.
- VPS:
  - `BASE_URL=http://127.0.0.1 bash scripts/verify_critical_http_paths.sh` -> `9 passed, 0 failed`
  - `bash scripts/verify_stable_release_vps.sh` -> `PASS`

## Residual Risk

- `ecdsa` timing-attack advisory currently has no upstream patch.
- `starlette` still flagged by scanner; app-level `Range` guard reduces exploitability on this stack while upgrade planning continues.
- `pip` upgrade available and should be applied in controlled maintenance window.

## Outcome

Phase 32 completed with targeted HTTP header hardening, stable security scan reporting, and full regression confirmation without behavior breakage.
