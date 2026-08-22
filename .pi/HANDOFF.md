# Project Handoff

## Context Contract

This is the repository's only active session checkpoint. `AGENTS.md`, source code, and current manifests are authoritative; other snapshots are historical.

## Current Objective

Prepare SIAB1 for deployment to a new VPS at `siab.man1rokanhulu.cloud` from the canonical repository at `https://github.com/kuker24/SIAB1`.

## Current State

- Project identity is `SIAB1` / `Sistem Informasi Asesmen Berintegritas`.
- Technical slug, Compose project, database, images, and monitoring labels use `siab1`.
- Android native package is `id.siab1.kiosk`; Flutter fallback is `id.siab1.flutter`.
- Release clients require an explicit server URL; `siab1.invalid` is a non-release placeholder.
- Public hostname is `siab.man1rokanhulu.cloud`; Cloudflare remains authoritative DNS in DNS-only mode.
- SafeLine CE terminates public TLS and forwards to the loopback-only SIAB1 Nginx origin at `127.0.0.1:8080`.
- SafeLine management binds to `127.0.0.1:9443` and is accessed only through an SSH tunnel.
- Python/FastAPI and Flutter remain supported fallbacks.
- Legacy phase reports, stale deployment scripts, duplicate client sources, and unused web assets were removed after consolidation.
- New VPS host details, SSH identity, capacity validation, DNS cutover, and runtime deployment are pending. No VPS cutover has been performed.

## Verification Evidence

- **PASS** - full Python suite: 487 tests.
- **PASS** - `python scripts/check_security.py` and release gate with `SKIP_HTTP=1`.
- **PASS** - Go test, vet, and build.
- **PASS** - Android kiosk Kotlin compile and lint.
- **PASS** - Compose config, shell syntax, and shellcheck.
- **PASS** - SIAB1 identity guard and local documentation-link guard.
- **NOT RUN** - HTTP smoke because no local service was started.
- **NOT CONFIGURED** - Flutter SDK is not available in the current PATH.

## Remaining Decisions

- Validate the SafeLine and SIAB1 Compose topology, DNS, TLS, CORS, and client release configuration on the new VPS.
- Validate sizing and deployment state directly on the new VPS before cutover.
- Build and smoke-test the signed Android release against `siab.man1rokanhulu.cloud`.
- Run Flutter verification when the SDK is available.

## Production Safety Boundary

- Do not read or expose environment files, keys, tokens, certificates, participant answers, or credentials.
- Do not deploy, publish assessments, restart services, migrate data, or run heavy tests without explicit approval and a verified backup.
