# AGENTS.md
Guidance for coding agents in this repository. Root DOX contract. Keep current and concise; do not add daily logs.

## Project Purpose
SIAB1 (Sistem Informasi Asesmen Berintegritas) provides protected assessment delivery, administrative control, monitoring, and reporting. Backend and kiosk clients enforce integrity controls including SEB/SXB validation, anti-abuse controls, and audit logging.

## Project State
- Status: **ESTABLISHED**. Entry points, production orchestration, test suite, and stable domain boundaries exist.
- Canonical repository: `https://github.com/kuker24/SIAB1`; it starts from a clean root commit and does not inherit the legacy repository history.
- Map state: **CURRENT** after this refresh; VPS facts below are documented snapshots, not live-host evidence.
- Root map supersedes stale notes from prior AI runs. No child DOX is currently needed.
- Context contract: this file is the durable project map; `.pi/HANDOFF.md` is the only active session checkpoint. Treat every other AI handoff, save, snapshot, or progress note as historical unless that checkpoint explicitly promotes it.

## Technology
- Backend: Python 3.11, FastAPI `0.135.1`, async SQLAlchemy `2.0.48`, PostgreSQL, Redis, Celery `5.6.2`, and Nginx.
- Production images: PostgreSQL `15-alpine`, Redis `7-alpine`, Prometheus `v2.53.0`, Grafana `11.1.0`.
- Client: Flutter at `flutter_client_code`; entry `flutter_client_code/lib/main.dart`; package version `2.0.0+2`; Dart SDK `>=3.0.0 <4.0.0`.

## Entry Points
- API application: `app/main.py`.
- Configuration: `app/config.py`; settings read from `.env`. Never read or print environment secrets.
- Database wiring: `app/database.py`.
- High-impact API path: `app/api/exams.py`.
- Production orchestration: `docker-compose.production.yml`.
- Flutter application: `flutter_client_code/lib/main.dart`.

## Repository Structure
- `app/api`: API routes.
- `app/core`: shared runtime, policy, and operational logic.
- `app/middleware`: HTTP security, SXB enforcement, logging, rate limiting, and performance middleware.
- `app/models`: SQLAlchemy ORM models.
- `app/schemas`: Pydantic request and response schemas.
- `app/services`: application services.
- `app/tasks`: Celery tasks and scheduler.
- `flutter_client_code`: Flutter student client.
- `docker`: production Dockerfiles, Nginx config, certificates mount path, and database initialization.
- `scripts`: maintenance, security, release-gate, and VPS-readiness commands.
- `monitoring`: Prometheus and Grafana configuration.
- `tests`: committed pytest suite; 63 files at mapping snapshot.
- `docs`: operational, deployment, validation, and historical documentation.

## Global Contracts
### Python and API
- Use Python 3.11 semantics, four-space indentation, explicit public and non-trivial return types, and readable lines preferably <=100 characters.
- Keep endpoint functions slim. Put heavier logic in helpers or services.
- Import order: standard library, third-party, local `app.*`. Remove unused imports and dead code.
- Use Pydantic schemas and field constraints for request/response payloads. Keep routes consistent with `/api/...` patterns.
- Use `AsyncSession`; use `get_db_read()` for SELECT and `get_db_write()` for INSERT, UPDATE, and DELETE. Preserve dependency-managed transaction and rollback behavior.
- Return accurate `HTTPException` status codes with user-safe messages. Log unexpected errors with context and `exc_info=True`; do not leak internals or stack traces.

### Security and runtime
- Preserve SEB/SXB enforcement and validation flow; sanitization, rate limiting, account lockout, CAPTCHA, and audit logging are security contracts.
- Exam JWT expiry is intentionally 120 minutes. Do not shorten without explicit product decision.
- `redirect_slashes=False` prevents 307 body-loss issues.
- HTTPS redirect middleware remains disabled for Cloudflare SSL termination.
- Middleware add order in `app/main.py` is critical; Starlette executes it in reverse add order:
  1. `CORSMiddleware`
  2. `SecurityHeadersMiddleware`
  3. `RateLimitMiddleware` unless `DISABLE_RATE_LIMIT=true`
  4. `SXBEnforcerMiddleware`
  5. `LoggingMiddleware`
  6. `PerformanceMonitoringMiddleware`
- Keep Redis/Celery wiring aligned with task scheduler configuration. Celery results expire in 3600s and are ignored by default.
- Production origin serves `/static/` from Nginx disk (`alias`); critical exam JS stays `no-store`. Prometheus exporters (postgres, redis, nginx, node) must stay `up`.
- Postgres production budget is `shared_buffers=512MB` / 1536M limit. Do not restore `2560MB` without a measured working-set need. Student API `--workers 2` stays for burst.
- `DEBUG=true` and `DISABLE_RATE_LIMIT=true` are development-only. Telegram alerts require configured `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_IDS`.

## Common Commands
### Local API
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
python -m app.main
# Alternative
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Production Compose
```bash
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs -f api
```

Rebuild only with explicit operational intent; do not run it during live exams:
```bash
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml build --no-cache
docker compose -f docker-compose.production.yml up -d
```

## Verification
- Syntax/static baseline:
```bash
python -m compileall app
python scripts/check_security.py
```
- Optional when installed: `ruff check app scripts`, `mypy app`.
- Full tests:
```bash
pytest -q
```
- Target a test file, function, or class method with normal pytest node IDs.
- Smoke/system check:
```bash
python scripts/system_check.py
```
- Release gate runs regression tests, security audit, and HTTP smoke:
```bash
bash scripts/verify_release_gate.sh
SKIP_HTTP=1 bash scripts/verify_release_gate.sh
```
- VPS runtime readiness:
```bash
bash scripts/verify_stable_release_vps.sh
```

## VPS Deployment Map
The production stack is deployed on the target VPS. The facts below were verified read-only on 2026-08-22 and remain a documented snapshot rather than continuous monitoring evidence.

- SIAB1 is deployed at `/opt/siab1`; SafeLine is deployed at `/opt/safeline`.
- Compose project, database, monitoring cluster, and image names use the `siab1` slug.
- Traffic contract: domain -> SafeLine -> loopback-only Nginx -> student or admin/control API lanes -> PgBouncer -> PostgreSQL. Service health path: `/health`.
- Nginx fronts eight student lanes (`api` through `api8`) and two isolated admin/control lanes (`api_admin`, `api_admin2`).
- Supporting services: PostgreSQL, PgBouncer, Redis, Celery worker, Celery beat, Prometheus, Grafana, and postgres/redis/nginx/node exporters. Optional `db_replica` is Compose profile `scaling`.
- Public hostname is `siab.man1rokanhulu.cloud`. Cloudflare provides authoritative DNS in DNS-only mode; SafeLine terminates public TLS and forwards to `127.0.0.1:8080`.
- SafeLine management binds to `127.0.0.1:9443` and must be accessed through an SSH tunnel. Never expose the management port publicly.
- The verified host has 16 vCPU, 15 GiB RAM, 4 GiB swap, and a 58 GiB root filesystem. All SIAB1 and SafeLine containers were running; public and origin health returned HTTP 200.
- Required environment and secrets remain outside documentation and Git. Production sets `DEBUG=false`, `APP_ENV=production`, and `ENFORCE_SXB=true`.

## Known Constraints
- Controlled 620-user public load passed correctness gates, but p95 latency under synchronized
  bursts remains high and must be monitored during real waves.
- Automated backup, restore drill, and guarded stateless restart are configured. Restart entries
  use a finite horizon and must be refreshed before expiry.
- Heavy exports are intentionally disabled in production peak mode; their success-path requires
  an approved maintenance window.
- The deployment directory is a file-based release rather than a Git checkout; generate a
  checksum release manifest after each synchronization.
- Android `2.0.2+4` still requires release signing material and physical-device smoke.
- Never release a client that still uses the `siab1.invalid` placeholder.
- Never use `docker compose ... down -v` on production without explicit, verified backup and approval. It removes persistent volumes.

## Child DOX Index
- None.
- Add child `AGENTS.md` only when an area gains durable ownership, local contracts, dedicated verification, or enough complexity to make root guidance insufficient.

## Agent Working Rules
- Prefer small, surgical changes. Do not overwrite unrelated user work.
- Read root `AGENTS.md`, then any child `AGENTS.md` on target path before edits.
- Validate changes with nearest runnable check: compile, targeted pytest, release gate, or relevant smoke check.
- Do not delete tooling or infrastructure directories without explicit request.
- Do not read `.env`, API keys, tokens, certificates, passwords, cookies, or other private data.
- Do not use `git reset --hard`, `git clean`, force push, commit, push, tag, release, or deploy without explicit request.
- Cursor rules (`.cursor/rules/`, `.cursorrules`) and Copilot instructions (`.github/copilot-instructions.md`) were absent at mapping snapshot. Treat them as additional constraints if later added.
