# Project Handoff

## Context Contract

This is the repository's only active session checkpoint. `AGENTS.md`, source code, and current manifests are authoritative; other snapshots are historical.

## Current Objective

None. Student hot-path closeout is complete. Do not reopen Go routing, START/JOIN/ANSWER handlers, or live canary files without explicit ops intent.

## Current State

- Repo: `/home/fahmiagent/Downloads/LAB GITHUB/LAB_Transformation/SIAB1/SIAB1`.
- Branch `provenance/migration-reconciliation`. Closeout commit `2856e47dca8c4e6105825ebc552f31d031fd7058` (`scripts/go_hotpath_lifecycle.py` only).
- Production `/opt/siab1`: Go image `siab1-go:373c131` healthy. Six student routes GO 100% (join, start, submit-answer, auto-save, auto-save-batch, submit). FastAPI fallback remains in nginx maps and `go_start_backend` backup.
- VPS rerun of `2856e47` (2026-08-28): lifecycle PASS; mixed-50 50/50 100%; 5xx=0; 429=0; lost/dups/live/wrong/missing=0; Redis PASS; PgBouncer `cl_waiting=0` `maxwait=0`; origin/public `/health` 200/200.
- Codebase Memory project: `SIAB1-clean`.
- Leave dirty: `.scratch/`, `scripts/go_remaining_stage0.py`, `scripts/build_card_users_csv.py`, `scripts/sync_school_users.py`, their tests, `docker/Dockerfile.go-test`.

## Verification Evidence

- **PASS** - single lifecycle through nginx (`HOTPATH_MIXED=0`): all replicas `go-start`, score 100, redis PASS, cleanup PASS.
- **PASS** - mixed-50 paced closeout (`HOTPATH_MIXED=50`): correctness 100%; service p50 310.018 / p95 402.694 / p99 524.476 / max 524.476; wall 87.996s.
- **PASS** - canary files 100pct for all six routes; FastAPI fallback AVAILABLE; rollback not invoked.
- Docs refreshed to match this topology: `AGENTS.md`, `ARCHITECTURE.md`, `README.md`, `docs/HISTORY.md`.

## Remaining Decisions

- Android `2.0.2+4` still needs signing material and physical-device smoke. Never ship `siab1.invalid`.
- Synchronized-burst p95 stays a watch item on real exam waves.
- Heavy export success-path only in an approved maintenance window.
- Repo Compose still marks `go_server` as profile `native-lean`; live routing is the canary maps, not that comment.
- Do not commit the leftover dirty files unless an operator asks.

## Production Safety Boundary

- Do not read or expose environment files, keys, tokens, certificates, participant answers, or credentials.
- Do not deploy, publish assessments, restart services, migrate data, or run heavy tests without explicit approval and a verified backup.
- Do not use `docker compose ... down -v` on production.
- Do not overwrite `runtime_control/nginx.*-canary.conf`. Dual-write answers is forbidden. Rollback is a per-route canary swap to FastAPI.
