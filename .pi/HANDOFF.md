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
- Native Android `2.0.1` build 3 is present on the VPS and its checksum is valid. Source
  `2.0.2+4` is ready but remains unsigned.
- Python/FastAPI and Flutter remain supported fallbacks.
- Legacy phase reports, stale deployment scripts, duplicate client sources, and unused web assets were removed after consolidation.

## Verification Evidence

- **PASS** - full Python suite: 504 tests.
- **PASS** - `python scripts/check_security.py` and release gate with `SKIP_HTTP=1`.
- **PASS** - Go test, vet, and build.
- **PASS** - Android kiosk Kotlin compile and lint.
- **PASS** - Compose config, shell syntax, and shellcheck.
- **PASS** - SIAB1 identity guard and local documentation-link guard.
- **PASS** - GitHub production hardening workflow through commit `ecc468b`.
- **PASS** - read-only VPS audit: 16 vCPU, 15 GiB RAM, 4 GiB unused swap, healthy SIAB1 containers, healthy ops summary, and 100% Redis stability.
- **PASS** - DNS, Let's Encrypt TLS, origin health, and public health; both health paths returned HTTP 200.
- **PASS** - automated daily backup and weekly non-destructive restore drill.
- **PASS** - weekly stateless auto-restart schedule, host-control path, and dry-run safety guard.
- **PASS** - controlled public load phases 50, 200, and 620 with 100% start/answer/submit.
- **PASS** - public violation/WebSocket smoke and upload smoke with synthetic cleanup.
- **PASS** - read-only capacity snapshot under root without weakening secret permissions.
- **PASS** - Flutter analyze and widget test using an isolated stable SDK.
- **POLICY BLOCKED** - export success-path while peak mode disables heavy exports; HTTP 503 guard verified.
- **BLOCKED** - signed Android `2.0.2+4` release; signing material is unavailable.
- **NOT RUN** - physical-device APK/SXB smoke on 1-3 Android devices.

## Remaining Decisions

- Build and publish signed Android `2.0.2+4` when release signing material is available.
- Run physical-device APK/SXB smoke on 1-3 representative Android devices.
- Test export success-path only during an approved maintenance window with peak mode disabled.
- Refresh the finite weekly auto-restart entries before the current schedule horizon expires.

## Production Safety Boundary

- Do not read or expose environment files, keys, tokens, certificates, participant answers, or credentials.
- Do not deploy, publish assessments, restart services, migrate data, or run heavy tests without explicit approval and a verified backup.
