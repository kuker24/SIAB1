# Phase 4.3.2D — Approved Isolated Staging Provisioning

Dokumen ini mencatat status Phase 4.3.2D. Walaupun nama fase adalah "Approved", eksekusi provisioning tetap wajib menunggu approval eksplisit sesuai scope yang diminta.

Phase ini **bukan Phase 5**, **bukan production rollout**, dan **bukan direct 100/300/600 execution**.

## 1. Latest Reviewed GitHub State

Latest reviewed baseline before this work:

```text
0c3b213d0ec818f387e6bf91306a20a10aaac958 docs: record approval-gated staging provisioning status
```

No new GitHub commit was found after that baseline before this Phase 4.3.2D work started.

## 2. Approval Status

```text
Operator approval for Phase 4.3.2D provisioning: no explicit approval found in the prompt
```

Approved target option:

```text
none
```

Approved scope:

- read-only GitHub/VPS verification;
- local tooling checks;
- docs/status update;
- publishing sanitized progress to GitHub.

Not approved:

- separate staging VM/VPS provisioning;
- same-VPS `ujian_staging` compose provisioning;
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

Decision: provisioning was not performed because approval was not explicit.

## 3. Preflight Production Safety

Read-only VPS check time:

```text
Thu Jun 4 00:41:40 WIB 2026
```

System aggregate:

| Metric | Value |
|---|---:|
| Uptime | 35 min |
| Load average | 0.32 / 0.21 / 0.24 |
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
| 1 | 200 | 0.017853s |
| 2 | 200 | 0.017232s |
| 3 | 200 | 0.018031s |

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
| `instantaneous_ops_per_sec` | 52 |
| `rejected_connections` | 0 |
| `evicted_keys` | 0 |
| `used_memory_human` | 14.03M |
| `maxmemory_human` | 1.37G |

No raw answer, token, session, or PII was exported.

## 4. Target Classification

Current target classification remains:

```text
production live stack only; isolated staging target does not exist
```

Evidence:

- only production `ujian_online-*` containers were found;
- no `ujian_staging` compose project was found;
- only public Nginx ports 80/443 are exposed;
- non-template PostgreSQL databases visible: `exam_system`, `postgres`;
- no staging API port `127.0.0.1:18080` exists;
- no separate staging DB/schema/database was verified;
- no separate staging Redis container/namespace was verified.

Decision:

- production live stack must not be used for direct 100/300/600;
- Phase 4.3.2D cannot provision without explicit Option A or Option B approval.

## 5. Staging Provisioning Status

| Item | Status |
|---|---|
| Separate staging VM/VPS | not approved / not provisioned |
| Same-VPS `ujian_staging` compose | not approved / not provisioned |
| Staging API | not available |
| Staging DB | not available |
| Staging Redis | not available |
| Production Nginx changed | no |
| Production containers touched | no |
| Production DB written | no |
| Production Redis written | no |
| Public staging port exposed | no |

## 6. API Isolation Status

Status:

```text
not available
```

Required future state if approved:

- Option A: separate staging VM/VPS API target; or
- Option B: same-VPS staging API bound only to `127.0.0.1:18080`.

No staging API health check was possible.

## 7. DB Isolation Status

Status:

```text
not available
```

Required future state if approved:

- separate staging PostgreSQL container/database;
- staging-only credentials;
- no production DB write;
- no production data/token/session reuse.

## 8. Redis Isolation Status

Status:

```text
not available
```

Required future state if approved:

- separate staging Redis container preferred; or
- explicitly isolated Redis DB/namespace;
- no production token/session/queue key reuse.

## 9. Safe-Mode Validation

Production safe-mode sample remains direct/off:

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

Future staging target must also use direct/off safe-mode.

## 10. Tooling Readiness

Controlled local environment using latest branch helper:

```bash
python -m py_compile scripts/load_test_answer_sync.py
python scripts/load_test_answer_sync.py --help
.venv/bin/python -m pytest tests/test_load_test_answer_sync.py -q
```

Result:

```text
32 passed in 0.06s
```

Known VPS production tree blocker remains from earlier checks:

```text
ModuleNotFoundError: No module named 'httpx'
```

No package was installed on VPS and production runtime environment was not modified.

## 11. Synthetic Dataset / CSV Status

Synthetic dataset status:

```text
not created
```

CSV status:

```text
/tmp/ujianonline-direct-sessions-20260604.csv: not created
```

Reason:

- no isolated staging target;
- no explicit approval for staging provisioning/data preparation;
- production DB must not receive synthetic load data.

## 12. Dry-Run Status

Status:

```text
not executed
```

Reason:

- no staging API;
- no staging DB/Redis;
- no synthetic CSV;
- no explicit approval for provisioning/execution.

## 13. Direct Execution Status

| Tier | Status | Reason |
|---|---|---|
| direct-100 | not executed | no isolated staging target / no CSV / no execution approval |
| direct-300 | not executed | direct-100 not executed/pass |
| direct-600 | not executed | direct-300 not executed/pass |

No production load traffic was sent.

## 14. Final-Submit Sample Status

Status:

```text
not executed
```

Future endpoint for valid staging run:

```text
/api/student/exams/submit
```

## 15. Answer Consistency Status

Status:

```text
not executed
```

Reason:

- no synthetic execution;
- no staging DB;
- no synthetic session set.

## 16. Production Safety

No production mutation was performed:

- no production load test;
- no deploy;
- no restart/reboot;
- no migration;
- no container create/recreate/start/stop;
- no package install;
- no code sync;
- no DB/Redis write;
- no Nginx config change;
- no public port exposure;
- no APK/AAB build/upload;
- no raw answer/token/session/PII export.

## 17. Required Explicit Approval to Proceed

To proceed beyond this document, operator must explicitly approve exactly one option.

### Option A — Separate staging VM/VPS

Approval text should clearly state:

```text
I approve using a separate staging VM/VPS for Phase 4.3.2D isolated staging provisioning and non-production validation preparation.
```

### Option B — Same-VPS isolated compose staging

Approval text should clearly state:

```text
I approve same-VPS isolated compose staging for Phase 4.3.2D with:
- compose project ujian_staging;
- staging API bound only to 127.0.0.1:18080;
- separate staging DB/container or database;
- separate staging Redis container or isolated DB/namespace;
- no production Nginx change;
- no production DB write;
- no real student data;
- no APK build;
- no hybrid/queue/runtime-buffer;
- run only outside active exam windows;
- cleanup staging resources after tests.
```

If approval is ambiguous, provisioning remains blocked.

## 18. Rollback / No-Op Instruction

Current phase is no-op for production. No production rollback is needed.

If this documentation commit needs rollback:

```bash
git revert <this-commit-sha>
```

If staging is later approved/provisioned, rollback must only touch staging resources.

## 19. Decision

Phase 4.3.2D status:

```text
continue / blocked by missing explicit provisioning approval
```

Phase 5 status:

```text
still blocked
```
