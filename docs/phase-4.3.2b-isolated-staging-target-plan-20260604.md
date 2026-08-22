# Phase 4.3.2B — Isolated Staging / Non-Production Target Plan

Dokumen ini mencatat hasil review Phase 4.3.2B dan rencana provisioning target staging terisolasi untuk direct-mode validation 100 → 300 → 600.

Phase ini **bukan Phase 5**, **bukan production rollout**, dan **bukan production load test**.

## 1. Latest Reviewed GitHub State

Latest reviewed baseline before this Phase 4.3.2B check:

```text
d2697adee2284a0ca29eacd6f1424da70d0ca07f docs: record vps safe direct testing blocker
```

No new GitHub commit was found after that baseline before this work started.

## 2. Operator Approval Boundary

Operator has approved:

- VPS access for read-only verification and planning;
- publishing sanitized progress/status to GitHub.

Operator has **not explicitly approved** the following changes yet:

- create/recreate/start/stop containers;
- `docker compose up/down` for staging;
- package install on VPS;
- code sync/deploy;
- DB creation/migration/schema write;
- Redis provisioning/write;
- Nginx config/public port changes;
- production live load test;
- synthetic write load against production DB;
- APK/AAB build/upload;
- hybrid/queue/runtime-buffer activation.

Decision for this phase: produce a provisioning plan and stop before making changes.

## 3. VPS Read-Only State

Check time:

```text
Thu Jun 4 00:29:42 WIB 2026
```

System aggregate:

| Metric | Value |
|---|---:|
| Uptime | 23 min |
| Load average | 0.24 / 0.17 / 0.26 |
| RAM total | 15 GiB |
| RAM available | 11 GiB |
| Swap used | 0 B |
| Root disk usage | 47% |

Exam/session aggregate:

| Check | Result |
|---|---:|
| Active published exam windows | 0 |
| `exam_sessions.status='in_progress'` | 0 |

Upcoming published exam windows aggregate:

| Start WIB | End WIB | Exam count |
|---|---|---:|
| 2026-06-04 07:30 | 2026-06-04 09:00 | 4 |
| 2026-06-04 09:30 | 2026-06-04 11:00 | 2 |
| 2026-06-05 09:30 | 2026-06-05 11:00 | 1 |
| 2026-06-09 09:30 | 2026-06-09 11:00 | 1 |

Production containers were healthy at check time:

- 8 public API containers: healthy.
- 2 admin API containers: healthy.
- Nginx: healthy.
- PostgreSQL: healthy.
- PgBouncer: healthy.
- Redis: healthy.
- Celery worker/beat: healthy.
- Prometheus/Grafana: healthy.

Nginx local health:

| Attempt | HTTP | Time |
|---:|---:|---:|
| 1 | 200 | 0.020264s |
| 2 | 200 | 0.017817s |
| 3 | 200 | 0.021440s |

DB aggregate:

| Metric | Value |
|---|---:|
| Idle client connections | 60 |
| Active connections | 1 |
| Active queries over 5s | 0 |
| Idle-in-transaction sessions | 0 |

Redis aggregate:

| Metric | Value |
|---|---:|
| `instantaneous_ops_per_sec` | 101 |
| `rejected_connections` | 0 |
| `evicted_keys` | 0 |
| `used_memory_human` | 14.03M |
| `maxmemory_human` | 1.37G |

No raw answer, token, session, or PII was exported.

## 4. Safe-Mode Validation

Production API container env sample remains direct/off:

```env
ADMIN_MONITORING_DETAIL_LEVEL=summary
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
ANSWER_WRITE_MODE=direct
APK_BUILD_ENDPOINT_ENABLED=false
EXAM_PEAK_MODE=true
HEAVY_EXPORT_ENABLED=false
MOBILE_APK_PRIMARY=true
SEB_DEBUG_ENDPOINTS_ENABLED=false
SEB_DESKTOP_LEGACY_ENABLED=false
SEB_QR_ENABLED=false
TELEGRAM_ALERTING_ENABLED=false
VIOLATION_ASYNC_ENABLED=true
```

No hybrid/queue/runtime-buffer activation was observed.

## 5. Target Classification

Current target classification:

```text
Production live stack only + staging is provisionable only with explicit approval
```

Evidence:

- only production `ujian_online-*` containers were found;
- only production public Nginx ports 80/443 were exposed;
- non-template PostgreSQL databases visible: `exam_system`, `postgres`;
- no separate staging API service/port exists;
- no separate staging DB/schema exists;
- no separate staging Redis DB/container policy is verified;
- public route points to production live stack.

Decision:

- direct 100/300/600 must **not** run against the current production live stack;
- Phase 4.3.2B cannot perform provisioning until operator explicitly approves the scope;
- this document is the required provisioning plan and approval request.

## 6. Recommended Architecture

### Option 1 — Separate staging VM/VPS

Recommended as safest option.

Requirements:

- independent API process/container;
- independent PostgreSQL database;
- independent Redis;
- no production secrets;
- no real student data;
- load target not routed to production public domain;
- synthetic-only dataset;
- no production blast radius.

Pros:

- strongest isolation;
- avoids CPU/RAM/I/O contention with exam-day production;
- direct 100/300/600 can run without risking production hot path.

Cons:

- requires separate infrastructure.

### Option 2 — Same VPS, isolated Docker Compose project

Acceptable only with explicit approval and safe window.

Proposed isolation:

| Component | Proposed staging value |
|---|---|
| Compose project | `ujian_staging` |
| Network | separate Docker network, not joined to production app network unless required and approved |
| API binding | localhost-only, e.g. `127.0.0.1:18080` |
| PostgreSQL | separate staging DB/container or separate database `exam_system_staging` with staging-only credentials |
| Redis | separate Redis container preferred, or isolated Redis DB/namespace if explicitly approved |
| Nginx | unchanged; no public route by default |
| Env file | outside repo or ignored path; never committed |
| Dataset | synthetic-only |
| Load target | `http://127.0.0.1:18080` only |

Pros:

- can be provisioned without new VM;
- API/DB/Redis can be isolated from production data;
- avoids public exposure.

Cons:

- still shares host CPU/RAM/disk I/O with production;
- must not run during active exam window;
- direct 600 may create host contention if run too close to production exam hours.

### Option 3 — Same production app containers with separate DB/schema only

Not recommended and not acceptable for direct 100/300/600.

Reason:

- app process and hot path would still share production API workers;
- production live endpoint would receive load traffic;
- failure would affect real users.

## 7. Proposed Same-VPS Staging Scope Requiring Approval

If operator chooses Option 2, approval must explicitly cover only these reversible actions:

1. Create a non-production working directory outside the committed repo or with ignored artifacts only.
2. Create staging env file outside git, with no committed secrets.
3. Create staging Docker Compose project `ujian_staging`.
4. Start staging API bound to localhost-only port `127.0.0.1:18080`.
5. Start separate staging PostgreSQL container or create a separate staging database only if approved.
6. Start separate staging Redis container, preferred over sharing production Redis.
7. Keep production Nginx unchanged.
8. Keep production containers running and untouched.
9. Generate synthetic-only dataset in staging DB.
10. Generate sessions CSV under `/tmp` only.
11. Run load-test helper from latest branch in a controlled venv or local environment, not from stale production tree.
12. Run dry-run first.
13. Only then run direct-100 if all gates pass.

Explicitly out of scope unless separately approved:

- public port exposure;
- Nginx config changes;
- production DB writes;
- production data copy;
- production code sync/deploy;
- APK build/upload;
- hybrid/queue/runtime-buffer activation.

## 8. Staging Safe-Mode Env

Staging must use direct safe-mode matching production safety defaults:

```env
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
EXAM_PEAK_MODE=true
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
MOBILE_APK_PRIMARY=true
SEB_DESKTOP_LEGACY_ENABLED=false
SEB_QR_ENABLED=false
SEB_DEBUG_ENDPOINTS_ENABLED=false
APK_BUILD_ENDPOINT_ENABLED=false
TELEGRAM_ALERTING_ENABLED=false
HEAVY_EXPORT_ENABLED=false
```

Additional staging constraints:

- secrets must be staging-only;
- JWT/signing keys must not be copied into committed files;
- real student/user tokens must not be used;
- staging env file must be outside git or ignored.

## 9. Resource Impact and Safe Window

Current VPS resources appear sufficient at idle check time:

- RAM available: 11 GiB;
- disk available: 31 GiB;
- load average low.

However, because this is still the production host, direct load test on same VPS can compete for:

- CPU;
- disk I/O;
- network namespace resources;
- Docker daemon resources;
- PostgreSQL/Redis if not fully separated.

Safe-window rule:

- do not provision or run load tests during active exam windows;
- do not run direct-300/direct-600 close to 07:30 or 09:30 exam windows;
- direct-600 on same VPS should be done only after explicit operator approval and preferably after exam-day window ends.

## 10. Tooling Readiness

Controlled local environment using latest branch helper:

```bash
python -m py_compile scripts/load_test_answer_sync.py
python scripts/load_test_answer_sync.py --help
.venv/bin/python -m pytest tests/test_load_test_answer_sync.py -q
```

Result:

```text
32 passed in 0.04s
```

Known VPS production tree blocker from prior check:

```text
ModuleNotFoundError: No module named 'httpx'
```

Recommended execution approach:

- use latest branch helper from controlled local environment when possible; or
- create a dedicated temporary venv under `/tmp` only if approved; or
- sync latest helper into staging-only path only if approved.

Do not install packages into the production runtime environment without approval.

## 11. Synthetic Dataset Plan

Synthetic dataset must be created only in isolated staging/non-production target.

Minimum dataset:

- 600+ synthetic users;
- 600+ synthetic sessions;
- synthetic exam;
- synthetic questions/options;
- sessions initially `in_progress`;
- synthetic-only JWT/tokens;
- no real class roster;
- no real student usernames;
- no production sessions;
- no production answer rows.

Naming convention:

- users: `loadtest_student_20260604_*`;
- exam/title prefix: `LOADTEST_SYNTHETIC_20260604_*`;
- classes: `LOADTEST_X`;
- any Redis keys: prefix `loadtest:20260604:` if created.

CSV path:

```text
/tmp/ujianonline-direct-sessions-20260604.csv
```

CSV columns:

```csv
session_id,question_id,selected_option_id,token
```

Rules:

- CSV remains under `/tmp`;
- CSV is never committed;
- raw token values are not printed in logs/docs;
- summary JSON remains under `/tmp` and is not committed.

## 12. Dry-Run Gate

After staging target and CSV exist, dry-run first:

```bash
python scripts/load_test_answer_sync.py \
  --base-url http://127.0.0.1:18080 \
  --sessions-csv /tmp/ujianonline-direct-sessions-20260604.csv \
  --vus 100 \
  --duration-seconds 60 \
  --final-submit-sample-rate 0.02 \
  --final-submit-endpoint /api/student/exams/submit \
  --summary-json /tmp/ujianonline-direct-100-dryrun-summary.json
```

Expected:

- dry-run only;
- no HTTP traffic;
- production host rejection remains active;
- final-submit endpoint printed as `/api/student/exams/submit`;
- tokens masked;
- direct-mode safety printed.

## 13. Direct Execution Gates

Do not run direct-100 unless all are true:

- isolated staging target verified;
- staging API healthy;
- staging DB verified separate from production data;
- staging Redis verified separate or isolated;
- safe-mode direct/off verified;
- synthetic CSV exists under `/tmp`;
- tooling `--help` passes;
- dry-run passes;
- no active exam window;
- operator approval explicitly covers non-production test execution;
- target is not production public host/domain.

Escalation:

- direct-300 only after direct-100 and answer consistency pass;
- direct-600 only after direct-300 and answer consistency pass.

## 14. Answer Consistency Plan

Run SELECT-only aggregate checks against staging DB after each tier.

Allowed aggregate checks:

- total answer rows for synthetic sessions;
- answered question count per synthetic session;
- terminal status aggregate for final-submit sample;
- duplicate answer constraint/anomaly aggregate;
- score/terminal anomaly aggregate.

Forbidden:

- raw answer export;
- raw token/session export;
- real student data export;
- production DB checks for synthetic test results.

## 15. DB / PgBouncer / Redis Notes to Capture

For each future tier, collect sanitized aggregates only.

DB/PgBouncer:

- active connection count;
- idle-in-transaction count;
- active query over threshold count;
- prepared statement error count if observed;
- connection closed mid-operation count if observed;
- PgBouncer pool saturation/wait if enabled.

Redis:

- `instantaneous_ops_per_sec`;
- `rejected_connections`;
- `evicted_keys`;
- memory pressure;
- queue/backlog keys only if synthetic-prefixed and queue remains off.

## 16. Rollback Plan

For same-VPS isolated compose staging, rollback should be simple and reversible:

1. Stop staging compose project only.
2. Remove staging containers/network/volumes only after preserving non-sensitive aggregate results if needed.
3. Delete staging env file from non-git path.
4. Delete `/tmp/ujianonline-direct-sessions-20260604.csv`.
5. Delete `/tmp/ujianonline-direct-*-summary.json` after extracting sanitized metrics.
6. Remove synthetic staging DB/container/Redis container only.
7. Do not touch production containers, production DB, production Redis, or production Nginx.

## 17. NO-GO Conditions

Do not proceed if any are true:

- only production live stack is available;
- approval for provisioning is ambiguous;
- active exam window is near or ongoing;
- staging DB isolation cannot be proven;
- staging Redis isolation cannot be proven;
- production public domain is the target;
- real student data/tokens/sessions are needed;
- tooling `--help` fails in execution environment;
- synthetic CSV would need to be committed;
- queue/hybrid/runtime-buffer would need activation;
- APK build/upload is required.

## 18. Current Phase Status

| Item | Status |
|---|---|
| Latest GitHub delta reviewed | done |
| Production read-only health checked | done |
| Production live stack load-tested | no |
| Target classification | production live only; staging provisionable with approval |
| Existing isolated staging target | not found |
| Staging provisioned | no |
| Approval for provisioning | missing |
| Tooling latest branch local | pass |
| VPS production tree helper | blocked by missing `httpx`/tooling mismatch |
| Synthetic CSV | not created |
| Dry-run | not executed |
| direct-100 | not executed |
| direct-300 | not executed |
| direct-600 | not executed |
| final-submit sample | not executed |
| answer consistency | not executed |
| Phase 5 | blocked |

## 19. Approval Request

To move from Phase 4.3.2B plan to actual provisioning, operator must explicitly approve one target option:

### Preferred approval

Approve use of a separate staging VM/VPS.

### Alternative approval

Approve same-VPS isolated compose staging with this explicit scope:

- create `ujian_staging` compose project;
- bind staging API to localhost-only `127.0.0.1:18080`;
- create/use separate staging DB/container;
- create/use separate staging Redis container;
- no production Nginx change;
- no production DB write;
- no real student data;
- no APK build;
- no hybrid/queue/runtime-buffer;
- run only outside active exam windows;
- allow cleanup of staging resources after tests.

Without explicit approval, Phase 4.3.2B remains plan-only.

## 20. Decision

Phase 4.3.2B status:

```text
continue / blocked until isolated staging target is approved and provisioned
```

Phase 5 status:

```text
still blocked
```
