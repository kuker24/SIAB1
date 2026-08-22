# Phase 48 Report - Core Data/Cache Driver Upgrade

Date: 2026-03-07  
Environment: Local + VPS

## Scope

1. Upgrade DB async driver and Redis client to current major releases.
2. Validate behavior parity across local + VPS runtime.
3. Re-run strict release gate with HTTP smoke in production runtime.

## Changes

- Updated `requirements.txt`:
  - `asyncpg==0.31.0` (from `0.30.0`)
  - `redis==7.3.0` (from `5.0.1`)
- Rebuilt and recreated VPS services:
  - `api`, `api2`, `api3`, `api4`, `api5`, `api6`, `celery_worker`, `celery_beat`

## Verification

- Local:
  - `pytest -q tests` -> `102 passed`
  - `SKIP_OUTDATED_SECURITY_AUDIT=1 SKIP_HTTP=1 bash scripts/verify_release_gate.sh` -> `PASS`
- VPS:
  - `PYTHON_BIN=./scripts/python_in_api.sh STRICT_HOST_HARDENING=1 SKIP_HTTP=0 bash scripts/verify_release_gate.sh` -> `PASS`
  - HTTP smoke: `9 passed, 0 failed`
  - Runtime versions in `ujian_online-api-1`:
    - `asyncpg=0.31.0`
    - `redis=7.3.0`

## Outcome

Phase 48 completed with successful core driver upgrade and no regression in exam-critical paths.
