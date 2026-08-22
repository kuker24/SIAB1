# Phase 46 Report - VPS In-Container Security Env Forwarding

Date: 2026-03-07  
Environment: VPS (`ujian-vps`)

## Scope

1. Ensure security env flags from release gate are propagated into API container Python process.
2. Eliminate VPS discrepancy where skip-outdated mode was ignored in container checks.
3. Re-validate strict release gate with HTTP smoke.

## Changes

- Added wrapper script:
  - `scripts/python_in_api.sh`
  - Runs `docker exec ... python` in `ujian_online-api-1`.
  - Explicitly forwards:
    - `SECURITY_FAIL_ON_TELNET_CLIENT`
    - `SECURITY_SKIP_OUTDATED_CHECK`
    - `SECURITY_ACCEPTLIST_FILE`
- Deployed script to VPS and rebuilt API image so latest `scripts/check_security.py` is present in container.

## Verification

- VPS strict deterministic gate:
  - `PYTHON_BIN=./scripts/python_in_api.sh STRICT_HOST_HARDENING=1 SKIP_OUTDATED_SECURITY_AUDIT=1 SKIP_HTTP=0 bash scripts/verify_release_gate.sh`
- Result:
  - tests: `62 passed`
  - security: `PASS`
  - outdated section: correctly shows skip message (`SECURITY_SKIP_OUTDATED_CHECK=1`)
  - HTTP smoke: `9 passed, 0 failed`

## Outcome

Phase 46 completed. VPS release gate now behaves consistently with local mode toggles and remains exam-path safe.
