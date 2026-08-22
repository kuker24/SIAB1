# Phase 31 Report - Redis Stability Scoring Hardening

Date: 2026-03-07  
Environment: Local + VPS (`ujian-vps`)

## Scope

1. Reduce false warning/critical status caused by low Redis cache-hit ratio without system pressure.
2. Keep warning escalation active when pressure signal is real (timeouts, blocked clients, memory pressure).
3. Expose new tuning knobs through app config and production compose environment.

## Changes

- Redis scoring config extension:
  - `app/config.py`
  - Added `redis_cache_hit_penalty_requires_pressure`
  - Added `redis_cache_hit_penalty_high_volume_min_lookups`
- Production env propagation:
  - `docker-compose.production.yml`
  - Added `REDIS_CACHE_HIT_PENALTY_REQUIRES_PRESSURE`
  - Added `REDIS_CACHE_HIT_PENALTY_HIGH_VOLUME_MIN_LOOKUPS`
- Redis layer scoring logic hardening:
  - `app/core/ops_summary.py`
  - Added pressure-aware penalty gating and advisory-only low cache-hit path.
  - Added observability flags in output metrics:
    - `cache_penalty_allowed`
    - `cache_penalty_applied`
    - `cache_pressure_signal`
    - `cache_high_volume_signal`
- Test coverage:
  - `tests/test_ops_summary.py`
  - Added cases for low cache-hit with and without runtime pressure.

## Verification

- Local:
  - `./.venv/bin/python -m pytest -q tests/test_ops_summary.py` -> `7 passed`
  - `./.venv/bin/python -m pytest -q tests` -> `97 passed`
- VPS:
  - `bash scripts/verify_stable_release_vps.sh` (repeated checks) -> `PASS`, `redis_stability: 100.00%`

## Outcome

Phase 31 completed with more accurate Redis health scoring: low cache-hit is no longer over-penalized when system pressure is absent, while real pressure still triggers warning/critical escalation.
