# Phase 35 Report - VPS Release Gate Closure and CVE Drift Remediation

Date: 2026-03-07  
Environment: Local + VPS (`ujian-vps`)

## Scope

1. Execute VPS release gate with full checks (tests + dependency audit + critical HTTP smoke).
2. Close newly surfaced actionable CVEs discovered during VPS container audit.
3. Validate telnet exposure status on VPS and local host.

## Changes

- Dependency remediation for VPS image:
  - `requirements.txt`
  - Upgraded:
    - `Pillow` -> `12.1.1`
    - `cryptography` -> `46.0.5`
    - `wheel` -> `0.46.3`
- Security scanner portability hardening:
  - `scripts/check_security.py`
  - Added graceful fallback when system command is unavailable (`FileNotFoundError`, e.g. `ss` not present inside container).

## Verification

- Local:
  - `./.venv/bin/python -m pytest -q tests` -> `99 passed`
  - `./.venv/bin/python scripts/check_security.py` -> `SECURITY CHECK PASSED`
- VPS:
  - Rebuilt and recreated `api/api2/api3/api4/api5/api6/celery_worker/celery_beat` from updated source.
  - Runtime version checks in `ujian_online-api-1`:
    - `fastapi 0.135.1`
    - `starlette 0.52.1`
    - `pyjwt 2.10.1`
    - `cryptography 46.0.5`
    - `pillow 12.1.1`
    - `wheel 0.46.3`
  - Release gate command (container-backed python + HTTP smoke):
    - `PYTHON_BIN=/tmp/python-in-api BASE_URL=http://127.0.0.1 SKIP_HTTP=0 bash scripts/verify_release_gate.sh`
    - Result: `PASS`
      - tests: `59 passed`
      - dependency security audit: `PASS`
      - critical HTTP smoke: `9 passed, 0 failed`

## Telnet Hardening Status

- VPS host: `telnet` binary not found (already clean).
- Local CachyOS host: `telnet` present via package `inetutils`; removal requires interactive sudo authentication.

## Outcome

Phase 35 completed: VPS release gate now passes end-to-end with actionable CVE count reduced to zero in runtime container. Residual local host hardening action (inetutils removal) is identified and ready for privileged execution.
