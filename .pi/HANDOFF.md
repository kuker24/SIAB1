# Project Handoff

## Context Contract

This is the repository's only active session checkpoint. `AGENTS.md`, source code, and current manifests are authoritative; other snapshots are historical.

## Current Objective

Complete production readiness for the deployed SIAB1 stack at `siab.man1rokanhulu.cloud` from the canonical repository at `https://github.com/kuker24/SIAB1`.

## Current State

- Project identity is `SIAB1` / `Sistem Informasi Asesmen Berintegritas`.
- Technical slug, Compose project, database, images, and monitoring labels use `siab1`.
- Android native package is `id.siab1.kiosk`; Flutter fallback is `id.siab1.flutter`.
- Release clients require an explicit server URL; `siab1.invalid` is a non-release placeholder.
- Public hostname is `siab.man1rokanhulu.cloud`; Cloudflare remains authoritative DNS in DNS-only mode.
- SafeLine CE terminates public TLS and forwards to the loopback-only SIAB1 Nginx origin at `127.0.0.1:8080`.
- SafeLine management binds to `127.0.0.1:9443` and is accessed only through an SSH tunnel.
- SIAB1 and SafeLine are deployed at `/opt/siab1` and `/opt/safeline`; DNS cutover and public TLS are active.
- The deployed SIAB1 and SafeLine manifests and critical backend files match the canonical local sources by checksum.
- Native Android `2.0.1` build 3 is present on the VPS and its checksum is valid.
- Native Android `2.0.2+4` has been rebuilt with the original release key after a post-submit
  exit-to-home fix and reinstalled on the Xiaomi `2306EPN60G`; it has not been published.
- Python/FastAPI and Flutter remain supported fallbacks.
- Legacy phase reports, stale deployment scripts, duplicate client sources, and unused web assets were removed after consolidation.

## Verification Evidence

- **PASS** - full Python suite: 528 tests.
- **PASS** - `python scripts/check_security.py` and release gate with `SKIP_HTTP=1`.
- **PASS** - Go test, vet, and build.
- **PASS** - Android kiosk Kotlin compile and lint.
- **PASS** - Compose config, shell syntax, and shellcheck.
- **PASS** - SIAB1 identity guard and local documentation-link guard.
- **PASS** - GitHub production hardening workflow through readiness commit `d00062e`.
- **PASS** - read-only VPS audit: 16 vCPU, 15 GiB RAM, 4 GiB unused swap, healthy SIAB1 containers, healthy ops summary, and 100% Redis stability.
- **PASS** - DNS, Let's Encrypt TLS, origin health, and public health; both health paths returned HTTP 200.
- **PASS** - automated daily backup and weekly non-destructive restore drill.
- **PASS** - weekly stateless auto-restart schedule, host-control path, and dry-run safety guard.
- **PASS** - controlled public load phases 50, 200, and 620 with 100% start/answer/submit.
- **PASS** - public violation/WebSocket smoke and upload smoke with synthetic cleanup.
- **PASS** - read-only capacity snapshot under root without weakening secret permissions.
- **PASS** - Flutter analyze and widget test using an isolated stable SDK.
- **PASS** - deployed runtime checksum dry-run and full release manifest verification.
- **POLICY BLOCKED** - export success-path while peak mode disables heavy exports; HTTP 503 guard verified.
- **PASS** - signed Android `2.0.2+4`; package, version, production URL, APK alignment, and
  signer continuity with `2.0.1` were verified. SHA-256
  `44030edda5aad3622ff813a8b4b75657d4691117690963a975542f21e1685a0b`.
- **PASS** - native post-submit contract: `examSubmitted` now stops the WebView, clears auth,
  and calls `finishAndRemoveTask()` so `/student/` login never appears. Physical submit retest
  of this rebuilt APK is still pending.
- **PASS** - burst-latency apply 2026-08-26 (no `down -v`, zero live sessions): Nginx serves
  `/static/` from disk (critical JS still `no-store`); `start_exam_session` delegates to
  `_build_start_question_responses`; Prometheus exporters postgres/redis/nginx/node `up`;
  Celery `result_expires=3600` and `task_ignore_result=True`; student API `--workers 2`.
  Origin and public `/health` HTTP 200. Rollback copies at `/opt/siab1/*.bak-burst-20260826`.
- **PASS** - physical-device Android `2.0.2+4` smoke: clean install, cold launch, invalid and
  valid login/token flows, trusted native exam start, two-answer autosave, offline/reconnect,
  final submit with score, screen pinning, screenshot blocking, clean kiosk exit, and no
  crash/ANR/runtime error. The isolated synthetic exam/user/session and local credentials were
  removed after verification; the pre-smoke backup remains at
  `/opt/siab1/backups/pre-physical-smoke-20260826T052900.sql.gz` with its checksum sidecar.

## Remaining Decisions

- Back up the recovered release signing material to approved external private storage.
- Clarify whether trusted native sessions should populate `ExamSession.is_secure_app_verified`;
  native header enforcement passed, but this currently unused observability field remains false.
- Publish signed Android `2.0.2+4` only after explicit release approval.
- Test export success-path only during an approved maintenance window with peak mode disabled.
- Refresh the finite weekly auto-restart entries before the current schedule horizon expires.

## Production Safety Boundary

- Do not read or expose environment files, keys, tokens, certificates, participant answers, or credentials.
- Do not deploy, publish assessments, restart services, migrate data, or run heavy tests without explicit approval and a verified backup.
