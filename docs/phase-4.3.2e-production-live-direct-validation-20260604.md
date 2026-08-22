# Phase 4.3.2E — Operator-Approved Production-Live Direct-Mode Validation

Dokumen ini mencatat Phase 4.3.2E setelah operator memberi approval eksplisit untuk production-live direct-mode validation.

Phase ini **bukan Phase 5 rollout**, **bukan aktivasi hybrid/queue/runtime-buffer**, dan **bukan APK build**.

## 1. Latest Reviewed GitHub State

Latest reviewed baseline before this work:

```text
1f5790c02ff8569e24f6e8be19ff9fba7a2b3776 docs: record phase 4.3.2d staging approval blocker
```

No new GitHub commit was found after that baseline before this Phase 4.3.2E work started.

## 2. Operator Approval Status

Operator approval for Phase 4.3.2E was explicitly provided in chat:

```text
Approved.
VPS production/live may be used as the test target.
Testing must be done far from exam hours.
Backup exists and must be verified before write/load tests.
Goal is to complete the remaining validation phases.
```

Approval covers:

- controlled production-live direct-mode validation;
- synthetic/control data preparation if needed;
- direct-100, direct-300, direct-600 ramp testing;
- final-submit sample testing;
- answer consistency checks;
- DB/PgBouncer/Redis aggregate observation;
- sanitized documentation of results.

Approval does **not** cover:

- APK/AAB build/upload;
- weakening APK/SXB/header/signature validation;
- deleting cheating detection;
- deleting emergency/admin command;
- enabling hybrid/queue/runtime-buffer in production;
- schema migration unless separately approved;
- public endpoint contract changes;
- committing `.env`, tokens, CSV sessions, summary JSON, DB dump, backups, APK/AAB, or secrets;
- exporting raw answer/token/session/PII.

## 3. Production Preflight Safety Gate

Read-only VPS check time:

```text
Thu Jun 4 00:52:00 WIB 2026
Timezone: Asia/Jakarta (WIB, +0700)
```

System aggregate:

| Metric | Value |
|---|---:|
| Uptime | 45 min |
| Load average | 0.24 / 0.24 / 0.22 |
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

Container health at check time:

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
| 1 | 200 | 0.030693s |
| 2 | 200 | 0.021529s |
| 3 | 200 | 0.025255s |

DB aggregate:

| Metric | Value |
|---|---:|
| Total connections | 66 |
| Active connections | 1 |
| Active queries over 5s | 0 |
| Idle-in-transaction sessions | 0 |

Redis aggregate:

| Metric | Value |
|---|---:|
| `instantaneous_ops_per_sec` | 61 |
| `rejected_connections` | 0 |
| `evicted_keys` | 0 |
| `used_memory_human` | 14.03M |
| `maxmemory_human` | 1.37G |

No raw answer, token, session, or PII was exported.

## 4. Production Safe-Mode Validation

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

Safe-mode gate status:

```text
pass
```

No hybrid/queue/runtime-buffer activation was observed.

## 5. Backup Verification Gate

Backup discovery found the latest DB backup file:

| Field | Value |
|---|---|
| Latest backup name | `backup_20260603_021502.sql.gz` |
| Timestamp | 2026-06-03 02:15:06 WIB |
| Size | 9,946,454 bytes |
| Integrity check | `gzip -t`: pass |
| Restore procedure | documented in backup cron log |

Backup age at preflight time:

```text
approximately 22 hours 37 minutes
```

Backup gate decision:

```text
NO-GO for production-live write/load test
```

Reason:

- the latest verified backup predates 2026-06-03 official exam activity and later production metadata fixes;
- it is not a fresh snapshot of the current production state before synthetic writes/load;
- operator approval required backup verification before write/load tests;
- the instruction says to stop before write/load if backup is missing, stale, or uncertain.

Therefore, Phase 4.3.2E stopped before:

- synthetic data creation;
- sessions CSV generation;
- dry-run;
- direct-100/300/600;
- final-submit sample;
- answer consistency execution.

Recommended unblocker:

1. create or verify a fresh production DB backup after all current official exam data is present;
2. run integrity check;
3. document restore procedure;
4. obtain operator acceptance of the fresh backup status;
5. rerun Phase 4.3.2E gates before any synthetic write/load.

## 6. Data Strategy

Selected strategy:

```text
not executed
```

Planned strategy after fresh backup gate passes:

- controlled synthetic test data in production DB, clearly prefixed;
- no real student data;
- no official exam;
- no real class roster;
- tokens/session IDs stored only under `/tmp`;
- no raw tokens in docs;
- cleanup plan required.

Required synthetic prefixes:

- users: `loadtest_student_20260604_*`;
- exam/title: `LOADTEST_SYNTHETIC_20260604_*`;
- class: `LOADTEST_X`;
- Redis keys: `loadtest:20260604:*`.

## 7. Tooling Readiness

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

Known VPS production tree issue from earlier phases remains relevant:

```text
ModuleNotFoundError: No module named 'httpx'
```

No package was installed on VPS and no production runtime environment was modified.

## 8. CSV Status

CSV status:

```text
/tmp/ujianonline-direct-sessions-20260604.csv: not created
```

Reason:

- backup gate did not pass for production-live write/load testing.

No sessions CSV was committed.

## 9. Dry-Run Status

Status:

```text
not executed
```

Reason:

- no synthetic/control sessions CSV;
- stopped at backup gate.

## 10. Direct Execution Status

| Tier | Status | Reason |
|---|---|---|
| direct-100 | not executed | stopped at backup gate |
| direct-300 | not executed | direct-100 not executed/pass |
| direct-600 | not executed | direct-300 not executed/pass |

No production load traffic was sent.

## 11. Final-Submit Sample Status

Status:

```text
not executed
```

Future endpoint when gates pass:

```text
/api/student/exams/submit
```

## 12. Answer Consistency Status

Status:

```text
not executed
```

Reason:

- no synthetic execution;
- no synthetic answer rows;
- stopped at backup gate.

## 13. DB / PgBouncer Notes

Read-only preflight aggregate:

- DB total connections: 66;
- DB active connections: 1;
- active queries over 5s: 0;
- idle-in-transaction sessions: 0;
- PgBouncer container healthy.

No write pressure test was run.

## 14. Redis Notes

Read-only preflight aggregate:

- ops/sec: 61;
- rejected connections: 0;
- evicted keys: 0;
- used memory: 14.03M;
- maxmemory: 1.37G;
- Redis container healthy.

No synthetic Redis keys were created.

## 15. Cleanup Status

Cleanup required:

```text
none
```

Reason:

- no synthetic data created;
- no CSV/summary JSON created;
- no DB/Redis writes performed.

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

## 17. Risk Assessment

Current phase risk: low.

Reason:

- only read-only production checks were run;
- backup integrity was checked via gzip only;
- local tooling checks were run;
- no production write/load action was performed.

Future risk if proceeding without fresh backup: high.

Reason:

- existing latest verified backup is stale relative to current production state;
- a rollback from that backup could lose official exam data/metadata changes made after 2026-06-03 02:15 WIB.

## 18. Rollback / No-Op Instruction

Current phase is no-op for production. No production rollback is needed.

If this documentation commit needs rollback:

```bash
git revert <this-commit-sha>
```

If a fresh backup is created later, do not commit the backup file and do not export it.

## 19. Decision

Phase 4.3.2E status:

```text
continue / blocked at backup freshness gate
```

Phase 5 status:

```text
still blocked
```

Phase 5 may **not** be proposed yet because direct-100/300/600, final-submit sample, and answer consistency have not executed/pass.

Next required action:

```text
Fresh production DB backup verification and operator acceptance before any synthetic write/load test.
```
