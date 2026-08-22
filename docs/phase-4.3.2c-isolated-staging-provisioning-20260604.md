# Phase 4.3.2C — Approval-Gated Isolated Staging Provisioning

Dokumen ini mencatat status Phase 4.3.2C: approval-gated provisioning untuk target isolated staging/non-production.

Phase ini **bukan Phase 5**, **bukan production rollout**, dan **bukan direct load execution**.

## 1. Latest Reviewed GitHub State

Latest reviewed baseline before this work:

```text
d5fe2475408f628bfc7d37ca7d05a18754629a4e docs: plan isolated staging target for direct validation
```

No new GitHub commit was found after that baseline before this Phase 4.3.2C work started.

## 2. Approval Status

```text
Operator approval for Phase 4.3.2C provisioning: no
```

Approved scope:

- read-only VPS verification;
- docs/status update;
- publishing sanitized progress to GitHub.

Not approved:

- create/recreate/start/stop containers;
- `docker compose up/down`;
- package install on VPS;
- code sync/deploy;
- DB/schema/database creation;
- Redis provisioning/write;
- Nginx config change;
- public port exposure;
- synthetic data writes;
- production live load test;
- direct-100/300/600 execution;
- APK/AAB build/upload;
- hybrid/queue/runtime-buffer activation.

Decision: Path A is active. No provisioning action was performed.

## 3. Preflight Production Safety

Read-only check time:

```text
Thu Jun 4 00:35:55 WIB 2026
```

System aggregate:

| Metric | Value |
|---|---:|
| Uptime | 29 min |
| Load average | 0.15 / 0.28 / 0.28 |
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

Production container health at check time:

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
| 1 | 200 | 0.019034s |
| 2 | 200 | 0.016718s |
| 3 | 200 | 0.020806s |

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
| `instantaneous_ops_per_sec` | 72 |
| `rejected_connections` | 0 |
| `evicted_keys` | 0 |
| `used_memory_human` | 14.03M |
| `maxmemory_human` | 1.37G |

No raw answer, token, session, or PII was exported.

## 4. Target Classification

Current target classification remains:

```text
Production live stack only; isolated staging is not provisioned
```

Evidence:

- only production `ujian_online-*` containers were found;
- only public Nginx ports 80/443 are exposed;
- non-template PostgreSQL databases visible: `exam_system`, `postgres`;
- no `ujian_staging` compose project was found;
- no staging API port `127.0.0.1:18080` exists;
- no separate staging DB/schema/database was verified;
- no separate staging Redis container/namespace was verified.

Decision:

- current VPS production live stack must not be used for direct 100/300/600;
- same-VPS isolated staging is provisionable only after explicit approval.

## 5. Staging Provisioning Status

| Item | Status |
|---|---|
| Existing isolated staging target | not found |
| Provisioning approval | missing |
| Staging provisioned | no |
| Production containers touched | no |
| Production Nginx changed | no |
| Production DB written | no |
| Redis provisioned/written | no |
| Public port exposed | no |

## 6. API / DB / Redis Isolation Status

API isolation:

```text
not available yet
```

Required future state:

- separate staging API;
- localhost-only target, e.g. `http://127.0.0.1:18080`;
- no public Nginx route unless separately approved.

DB isolation:

```text
not available yet
```

Required future state:

- separate staging DB/container preferred; or
- explicit staging database such as `exam_system_staging` with staging-only credentials;
- no production data copy unless sanitized and explicitly approved;
- no production answer/student/session writes.

Redis isolation:

```text
not available yet
```

Required future state:

- separate staging Redis container preferred; or
- explicit isolated DB/namespace policy;
- no production Redis queue/session/token key reuse.

## 7. Safe-Mode Validation

Production API env sample remains direct/off:

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

Staging, when approved/provisioned, must use the same safe-mode posture:

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

## 8. Tooling Readiness

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

Known VPS production tree blocker from previous Phase 4.3.2A/4.3.2B remains relevant:

```text
ModuleNotFoundError: No module named 'httpx'
```

No package was installed on VPS and no production tree helper was modified.

Future execution should use one of:

1. latest branch helper from controlled local environment; or
2. approved temporary venv under `/tmp`; or
3. approved staging-only code/helper path.

Do not install Python packages into production runtime environment without approval.

## 9. Synthetic Dataset / CSV Status

Synthetic dataset status:

```text
not created
```

CSV status:

```text
/tmp/ujianonline-direct-sessions-20260604.csv: not created
```

Reason:

- no isolated staging target yet;
- no approval for staging DB/Redis writes;
- production DB must not receive synthetic load data.

Future requirements:

- 600+ synthetic users;
- 600+ synthetic sessions;
- synthetic exam/questions/options;
- synthetic-only JWT/tokens;
- sessions initially `in_progress`;
- no real class roster;
- no real student usernames;
- no production sessions/answers;
- CSV under `/tmp` only;
- no raw tokens in docs/logs;
- no CSV commit.

## 10. Dry-Run Status

Dry-run status:

```text
not executed
```

Reason:

- no isolated staging API target;
- no synthetic CSV;
- provisioning approval missing.

Future dry-run target must be staging only:

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

Expected future dry-run:

- no HTTP traffic;
- tokens masked;
- final-submit endpoint `/api/student/exams/submit`;
- direct-mode safety printed;
- production host rejection active.

## 11. Direct Execution Status

| Tier | Status | Reason |
|---|---|---|
| direct-100 | not executed | no isolated staging target / no CSV / no execution approval |
| direct-300 | not executed | direct-100 not executed/pass |
| direct-600 | not executed | direct-300 not executed/pass |

No production load traffic was sent.

## 12. Final-Submit Sample Status

Status:

```text
not executed
```

Future endpoint:

```text
/api/student/exams/submit
```

No token/session/answer was used in this phase.

## 13. Answer Consistency Status

Status:

```text
not executed
```

Reason:

- no synthetic execution;
- no staging DB;
- no synthetic session set.

Future checks must be SELECT-only aggregate against staging DB.

## 14. Exact Command Plan After Approval

The following is a command-level plan only. Do not run until explicit approval is given.

### Approval precondition

Operator should explicitly approve one of:

1. separate staging VM/VPS; or
2. same-VPS isolated compose staging with the exact scope below.

### Same-VPS isolated compose approval scope

If approved, scope should include:

- create `ujian_staging` compose project;
- bind staging API to `127.0.0.1:18080` only;
- create/use separate staging DB/container;
- create/use separate staging Redis container;
- keep production Nginx unchanged;
- keep production containers untouched;
- use staging-only env outside git;
- no production DB writes;
- no real student data;
- no APK build;
- no hybrid/queue/runtime-buffer;
- cleanup staging resources after tests.

### Pre-provisioning commands

Read-only preflight again:

```bash
date
uptime
free -h
df -h /
docker compose -f /root/ujian_online/docker-compose.production.yml ps
curl -sk https://127.0.0.1/health
```

Aggregate DB check only:

```sql
SELECT count(*) AS active_published_exam_windows
FROM exams
WHERE is_deleted IS NOT TRUE
  AND is_published IS TRUE
  AND now() BETWEEN start_time AND end_time;

SELECT status, count(*)
FROM exam_sessions
WHERE status='in_progress'
GROUP BY status;
```

### Provisioning outline

Use a staging-only directory, e.g.:

```text
/opt/ujianonline-staging
```

Create ignored/staging-only env file outside repo:

```text
/opt/ujianonline-staging/.env.staging
```

Create compose project name:

```text
ujian_staging
```

Required API binding:

```text
127.0.0.1:18080->8000/tcp
```

Do not edit production Nginx.

### Tooling venv option

If approved and needed:

```bash
python3 -m venv /tmp/ujianonline-loadtest-venv
/tmp/ujianonline-loadtest-venv/bin/python -m pip install -U pip
/tmp/ujianonline-loadtest-venv/bin/python -m pip install -r requirements.txt
```

Do not install globally.

### Post-provisioning verification

```bash
curl -sS http://127.0.0.1:18080/health
```

Verify staging env safe-mode:

```text
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
APK_BUILD_ENDPOINT_ENABLED=false
HEAVY_EXPORT_ENABLED=false
```

Verify DB/Redis isolation before any synthetic data.

## 15. Rollback Plan

If same-VPS staging is later approved/provisioned, rollback must only touch staging resources:

1. Stop staging compose project only.
2. Remove staging containers/network/volumes only after saving sanitized aggregate metrics if needed.
3. Delete staging env file from non-git path.
4. Delete `/tmp/ujianonline-direct-sessions-20260604.csv`.
5. Delete `/tmp/ujianonline-direct-*-summary.json` after extracting sanitized metrics.
6. Remove synthetic staging DB/container/Redis container only.
7. Do not touch production containers, production DB, production Redis, or production Nginx.

## 16. What Was Not Done

- No production restart/reboot.
- No deploy.
- No code sync.
- No migration.
- No container create/recreate/start/stop.
- No package install.
- No DB/Redis write.
- No Nginx change.
- No public port exposure.
- No production live load test.
- No direct 100/300/600.
- No APK/AAB build/upload.
- No raw answer/token/session/PII export.
- No CSV/summary JSON creation.
- No hybrid/queue/runtime-buffer activation.

## 17. Current Decision

Phase 4.3.2C status:

```text
continue / blocked by missing explicit provisioning approval
```

Phase 5 status:

```text
still blocked
```

To proceed, operator must explicitly approve either:

1. separate staging VM/VPS; or
2. same-VPS isolated compose staging with localhost API `127.0.0.1:18080`, isolated DB/Redis, no production Nginx change, no production DB write, staging-only env, and cleanup permission.
