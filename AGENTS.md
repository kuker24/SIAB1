# AGENTS.md
Guidance for coding agents in this repository. Root DOX contract. Keep current and concise; do not add daily logs.

## Project Purpose
Online exam system for protected student exam delivery, administrative control, monitoring, and reporting. Backend and Flutter client enforce exam-integrity controls including SEB/SXB validation, anti-abuse controls, and audit logging.

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
- Keep Redis/Celery wiring aligned with task scheduler configuration.
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
Documented deployment snapshot. Validate against target VPS before deployment.

- Host contract: Docker Compose production deployment for `man1rokanhulu.cloud`, path `/root/ujian_online`, Ubuntu `22.04.5 LTS` snapshot.
- User-verified canonical SSH access uses user `adminujian`, host `103.175.218.56`, and dedicated local key `~/.ssh/id_ed25519_ujian_online`:
```bash
ssh -i ~/.ssh/id_ed25519_ujian_online -o IdentitiesOnly=yes adminujian@103.175.218.56
```
- Keep the private key local; never copy it into the repository or VPS.
- Traffic: Cloudflare/domain -> Nginx -> student API lanes or admin/control API lanes -> PgBouncer -> PostgreSQL. Service health path: `/health`.
- Nginx fronts eight student lanes: `api` through `api8`; two isolated admin/control lanes: `api_admin` and `api_admin2`.
- Supporting services: PostgreSQL, PgBouncer, Redis, Celery worker, Celery beat, Prometheus, and Grafana. Optional `db_replica` is Compose profile `scaling`.
- Cloudflare Origin Certificate configuration uses `docker/certs/cloudflare-origin.crt` and `docker/certs/cloudflare-origin.key`, mounted into Nginx as `/etc/nginx/certs`.
- Required production environment and secret values must exist outside documentation. Production Compose sets `DEBUG=false`, `APP_ENV=production`, and `ENFORCE_SXB=true`; rate limiting is active unless explicitly disabled.

## Known Constraints and Documentation Drift
- Capacity snapshot risks: single-node PostgreSQL pressure, API replica limits near 960 MiB, PgBouncer pressure, and 60G disk assumptions. Revalidate all against target VPS capacity and workload.
- `DEPLOYMENT.md` contains stale or differing guidance: references `.env.production` not observed in current root mapping, `docker/ssl/` instead of active `docker/certs/`, an Nginx example different from active configuration, and legacy `docker-compose` syntax. This drift needs reconciliation; it does not prove deployment failure.
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
