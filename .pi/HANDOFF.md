# Project Handoff

## Context Contract

This is the repository's only active session checkpoint.

- `AGENTS.md` is the durable source of project rules, architecture map, and operational constraints.
- Source code and current manifests are authoritative for runtime facts.
- Other AI handoffs, snapshots, and progress documents are historical unless promoted here.

## Current Objective

Continue Native-Lean stabilization and release hardening from the clean repository at `https://github.com/kuker24/SIAB1`.

## Current State

- Project status: **ESTABLISHED**.
- Root `AGENTS.md`: **CURRENT**.
- The new repository intentionally starts with a clean root commit and excludes legacy Git history.
- Python/FastAPI and Flutter remain supported fallbacks; no VPS cutover is authorized.
- Native handlers cover the active DB-only/JSON route set identified by the parity audit.

## Verification Evidence

- **PASS** — full Python suite: 485 tests.
- **PASS** — `python scripts/check_security.py`.
- **PASS** — `SKIP_HTTP=1 bash scripts/verify_release_gate.sh`.
- **PASS** — Go test, vet, and build.
- **PASS** — frontend bundle reproducibility and JavaScript syntax checks.
- **PASS** — Python dependency audits for application and runtime lock files.
- **PASS** — focused Semgrep scan of the latest security-sensitive changes.
- **NOT RUN** — HTTP smoke because no local service was started.
- **NOT CONFIGURED** — Flutter SDK is not available in the current PATH.

## Remaining Risks

- The upstream advisory reported for `golang.org/x/crypto v0.52.0` has no fixed version at this checkpoint.
- Redis-backed multi-replica behavior and external integrations require their corresponding services for end-to-end validation.
- `DEPLOYMENT.md` retains documented drift around environment, certificate, Nginx, and Compose guidance.
- VPS deployment, restart, migration, and cutover remain approval-gated.

## Next Actions

1. Use the new GitHub repository as the canonical source for subsequent work.
2. Re-index the clean repository after the initial push.
3. Continue with the highest-priority Native-Lean or release-hardening gap supported by repository evidence.
4. Run HTTP and Flutter verification when their required runtimes are available.

## Production Safety Boundary

- Do not read or expose environment files, keys, tokens, certificates, participant answers, or credentials.
- Validate live VPS state before relying on documented snapshots.
- Do not deploy, publish exams, restart services, migrate data, or run heavy tests during active exams without explicit approval.
