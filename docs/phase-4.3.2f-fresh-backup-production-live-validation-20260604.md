# Phase 4.3.2F — Fresh Backup + Production-Live Direct Validation Rerun

Phase ini menjalankan controlled production-live direct-mode validation setelah fresh backup gate membuka blocker Phase 4.3.2E.

Phase ini **bukan Phase 5 rollout**, **bukan aktivasi hybrid/queue/runtime-buffer**, dan **bukan APK build**.

## 1. Latest Reviewed GitHub State

Latest reviewed head before this work:

```text
c0cc18db9f592163ba9d3a3a3f73ab72fe5f7a2c docs: record phase 4.3.2e backup gate blocker
```

No new GitHub commit was found after that baseline before Phase 4.3.2F execution.

## 2. Operator Approval Status

Operator approval was explicitly provided for production-live direct-mode validation, with these boundaries:

- VPS production/live may be used as target.
- Testing must be far from exam hours.
- Fresh backup must be verified before write/load tests.
- Scope includes synthetic/control data, direct 100/300/600, final-submit sample, answer consistency, and sanitized documentation.

Still not approved / not performed:

- APK/AAB build/upload;
- weakening APK/SXB/header/signature validation;
- deleting cheating detection or emergency/admin controls;
- enabling hybrid/queue/runtime-buffer;
- schema migration;
- public endpoint contract change;
- committing `.env`, token, CSV/session artifact, summary JSON, DB dump, backup, APK/AAB, or secrets;
- exporting raw answer/token/session/PII.

## 3. Fresh Backup Verification

A fresh production DB backup was created before synthetic write/load tests.

| Field | Value |
|---|---|
| Backup name | `backup_20260604_005915_pre_phase432f.sql.gz` |
| Backup category | production backup directory on VPS (`/root/ujian_online/backups`) |
| Timestamp | 2026-06-04 00:59:20 WIB |
| Size | 11,892,705 bytes |
| Integrity | `gzip -t`: pass |
| SHA256 prefix | `d667116498378c31` |
| Restore procedure | documented: `gunzip` pipe to `psql` after safe stop/start DB procedure |
| Backup committed/exported | no |

Operator backup acceptance:

```text
accepted: yes, under the Phase 4.3.2F approval to continue once a fresh verified backup exists
```

## 4. Production Preflight Safety Gate

Preflight after fresh backup:

```text
Thu Jun 4 00:59:42 WIB 2026
Timezone: Asia/Jakarta (WIB, +0700)
```

| Metric | Value |
|---|---:|
| Uptime | 53 min |
| Load average | 0.51 / 0.34 / 0.28 |
| RAM total | 15 GiB |
| RAM available | 11 GiB |
| Swap used | 0 B |
| Root disk usage | 47% |
| Active published exam windows | 0 |
| `exam_sessions.status='in_progress'` before synthetic data | 0 |

Upcoming official exam windows:

| Start WIB | End WIB | Exam count |
|---|---|---:|
| 2026-06-04 07:30 | 2026-06-04 09:00 | 4 |
| 2026-06-04 09:30 | 2026-06-04 11:00 | 2 |
| 2026-06-05 09:30 | 2026-06-05 11:00 | 1 |
| 2026-06-09 09:30 | 2026-06-09 11:00 | 1 |

Health:

- API containers: healthy.
- Admin API containers: healthy.
- Nginx: healthy.
- PostgreSQL: healthy.
- PgBouncer: healthy.
- Redis: healthy.
- Celery worker/beat: healthy.

Nginx health:

| Attempt | HTTP | Time |
|---:|---:|---:|
| 1 | 200 | 0.249906s |
| 2 | 200 | 0.016682s |
| 3 | 200 | 0.017020s |

DB/Redis baseline:

| Metric | Value |
|---|---:|
| DB total connections | 66 |
| DB active connections | 1 |
| DB idle-in-transaction | 0 |
| DB active queries over 5s | 0 |
| Redis ops/sec | 38 |
| Redis rejected connections | 0 |
| Redis evicted keys | 0 |
| Redis used memory | 14.02M |
| Redis max memory | 1.37G |

## 5. Production Safe-Mode Validation

Safe-mode sample remained direct/off:

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

No hybrid/queue/runtime-buffer activation occurred.

## 6. Data Strategy

Strategy used: controlled synthetic data in production DB after fresh backup.

Synthetic scope:

| Item | Count / Status |
|---|---:|
| Synthetic users | 650 |
| Synthetic sessions | 650 |
| Synthetic exam | 1, unpublished |
| Synthetic question | 1 |
| Synthetic options | 4 |
| Class | `LOADTEST_X` |
| CSV | `/tmp/ujianonline-direct-sessions-20260604.csv` |
| Raw tokens printed | no |
| Real student data used | no |

Prefixes:

- users: `loadtest_student_20260604_phase432f_*`;
- exam: `LOADTEST_SYNTHETIC_20260604_PHASE432F_*`;
- class: `LOADTEST_X`.

## 7. Tooling Readiness

Latest branch helper was copied to `/tmp` on VPS. Host had no `python3-venv`, so dependencies were installed with `pip --target` into `/tmp/ujianonline-phase432f-pydeps` only. No production runtime/global package install was performed.

Commands passed:

```bash
PYTHONPATH=/tmp/ujianonline-phase432f-pydeps python3 -m py_compile scripts/load_test_answer_sync.py
PYTHONPATH=/tmp/ujianonline-phase432f-pydeps python3 scripts/load_test_answer_sync.py --help
PYTHONPATH=/tmp/ujianonline-phase432f-pydeps python3 -m pytest tests/test_load_test_answer_sync.py -q
```

Result:

```text
32 passed in 0.16s
```

## 8. Dry-Run Result

Dry-run target:

```text
http://127.0.0.1
```

Dry-run result:

- no HTTP traffic;
- unique sessions: 650;
- token masked in output;
- direct/off safety printed;
- final-submit endpoint: `/api/student/exams/submit`;
- SEB config key hash supplied as header but not printed;
- dry-run summary JSON not created.

## 9. Direct-100 Result

Execution window:

```text
start: 2026-06-04T01:05:46+07:00
end:   2026-06-04T01:08:50+07:00
```

Overall:

| Metric | Value |
|---|---:|
| VUs | 100 |
| Duration | 180s |
| Total requests | 10,224 |
| Success | 10,224 |
| Failures | 0 |
| Status distribution | 200: 10,224 |
| Overall p50 | 193.98ms |
| Overall p95 | 492.20ms |
| Overall p99 | 1,903.34ms |
| Overall max | 5,109.23ms |

Per endpoint:

| Endpoint | Requests | Failures | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| `/api/exams/submit-answer` | 10,222 | 0 | 193.99ms | 492.22ms | 1,903.34ms | 5,109.23ms |
| `/api/student/exams/submit` | 2 | 0 | 145.16ms | 163.95ms | 165.62ms | 166.03ms |

Monitor aggregate:

| Metric | Max / Last |
|---|---:|
| Monitor samples | 34 |
| Load1 max | 10.63 |
| DB active max | 12 |
| DB idle-in-transaction max | 16 |
| DB active over 5s max | 0 |
| Redis rejected max | 0 |
| Redis evicted max | 0 |
| Redis memory last | 23.85M |

Consistency:

| Metric | Value |
|---|---:|
| Sessions total | 650 |
| Submitted sessions | 2 |
| In-progress sessions | 648 |
| Sessions with answers | 100 |
| Answer rows total | 100 |
| Max answers per session | 1 |
| Sessions with >1 answer | 0 |
| Terminal without answers | 0 |
| Terminal without score | 0 |
| Score out of range | 0 |

Direct-100 decision:

```text
functional/data pass
```

## 10. Direct-300 Result

Execution window:

```text
start: 2026-06-04T01:10:42+07:00
end:   2026-06-04T01:15:53+07:00
```

Overall:

| Metric | Value |
|---|---:|
| VUs | 300 |
| Duration | 300s |
| Total requests | 10,999 |
| Success | 10,999 |
| Failures | 0 |
| Status distribution | 200: 10,999 |
| Overall p50 | 4,832.75ms |
| Overall p95 | 18,497.75ms |
| Overall p99 | 28,242.38ms |
| Overall max | 53,663.94ms |

Per endpoint:

| Endpoint | Requests | Failures | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| `/api/exams/submit-answer` | 10,993 | 0 | 4,840.34ms | 18,498.30ms | 28,242.70ms | 53,663.94ms |
| `/api/student/exams/submit` | 6 | 0 | 118.79ms | 137.40ms | 138.54ms | 138.82ms |

Monitor aggregate:

| Metric | Max / Last |
|---|---:|
| Monitor samples | 58 |
| Load1 max | 11.93 |
| DB active max | 38 |
| DB idle-in-transaction max | 57 |
| DB active over 5s max | 0 |
| Redis rejected max | 0 |
| Redis evicted max | 0 |
| Redis memory last | 31.48M |

Consistency:

| Metric | Value |
|---|---:|
| Sessions total | 650 |
| Submitted sessions | 6 |
| In-progress sessions | 644 |
| Sessions with answers | 300 |
| Answer rows total | 300 |
| Max answers per session | 1 |
| Sessions with >1 answer | 0 |
| Terminal without answers | 0 |
| Terminal without score | 0 |
| Score out of range | 0 |

Direct-300 decision:

```text
functional/data pass, performance risk
```

## 11. Direct-600 Result

Execution window:

```text
start: 2026-06-04T01:16:50+07:00
end:   2026-06-04T01:22:05+07:00
```

Overall:

| Metric | Value |
|---|---:|
| VUs | 600 |
| Duration | 300s |
| Total requests | 11,033 |
| Success | 11,033 |
| Failures | 0 |
| Status distribution | 200: 11,033 |
| Overall p50 | 8,923.69ms |
| Overall p95 | 45,328.22ms |
| Overall p99 | 70,205.66ms |
| Overall max | 164,139.81ms |

Per endpoint:

| Endpoint | Requests | Failures | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|
| `/api/exams/submit-answer` | 11,027 | 0 | 8,932.11ms | 45,344.45ms | 70,218.83ms | 164,139.81ms |
| `/api/student/exams/submit` | 6 | 0 | 33.89ms | 36.55ms | 36.81ms | 36.88ms |

Monitor aggregate:

| Metric | Max / Last |
|---|---:|
| Monitor samples | 58 |
| Load1 max | 57.56 |
| DB active max | 143 |
| DB idle-in-transaction max | 138 |
| DB active over 5s max | 1 |
| Redis rejected max | 0 |
| Redis evicted max | 0 |
| Redis memory last | 35.96M |

Consistency:

| Metric | Value |
|---|---:|
| Sessions total | 650 |
| Submitted sessions | 6 |
| In-progress sessions | 644 |
| Sessions with answers | 600 |
| Answer rows total | 600 |
| Max answers per session | 1 |
| Sessions with >1 answer | 0 |
| Terminal without answers | 0 |
| Terminal without score | 0 |
| Score out of range | 0 |

Direct-600 decision:

```text
functional/data pass, performance NO-GO for rollout confidence
```

## 12. DB / PgBouncer / Redis Notes

Positive:

- No 4xx/429/499/5xx were observed in the helper summary.
- Final-submit samples returned 200 on `/api/student/exams/submit`.
- Answer consistency checks found no answer loss indication.
- Redis rejected connections remained 0.
- Redis evicted keys remained 0.
- DB state returned to normal after load.

Risk:

- Direct-300 already had answer p95 around 18.5s and p99 around 28.2s.
- Direct-600 had answer p95 around 45.3s, p99 around 70.2s, and max around 164.1s.
- Direct-600 monitor observed load1 max 57.56, DB active max 143, DB idle-in-transaction max 138, and active query over 5s max 1.
- Although the system recovered and no failures occurred, this is not a comfortable production UX margin.

## 13. Cleanup Status

Synthetic cleanup was performed with exact prefixes only.

Deleted aggregate:

| Item | Deleted |
|---|---:|
| Security events | 0 |
| User activity logs | 0 |
| Exam logs | 12 |
| Answers | 600 |
| Exam sessions | 650 |
| Question options | 4 |
| Questions | 1 |
| Exams | 1 |
| Users | 651 |

Cleanup verification:

| Check | Result |
|---|---:|
| Remaining synthetic users | 0 |
| Remaining synthetic exams | 0 |
| Global in-progress sessions after cleanup | 0 |
| Active published exam windows after cleanup | 0 |

Temporary sensitive artifacts were deleted from `/tmp` after extracting sanitized metrics:

- sessions CSV;
- SEB hash file;
- metadata file;
- summary JSON files;
- monitor CSV files;
- temporary helper/dependency directories.

No global Redis flush was performed.

Post-cleanup health:

| Metric | Value |
|---|---:|
| Nginx `/health` | 200 in 0.021977s |
| DB active connections | 1 |
| DB idle-in-transaction | 0 |
| DB active over 5s | 0 |
| DB total connections | 82 |
| Redis rejected connections | 0 |
| Redis evicted keys | 0 |
| Redis used memory | 33.76M |

## 14. Production Safety

Performed:

- fresh DB backup creation;
- synthetic/control DB data creation;
- production-live localhost direct-mode load test;
- exact-prefix synthetic cleanup;
- sanitized documentation.

Not performed:

- no APK/AAB build/upload;
- no deploy/code sync to production app;
- no production restart/reboot;
- no migration/schema change;
- no Nginx config change;
- no hybrid/queue/runtime-buffer activation;
- no raw answer/token/session/PII export;
- no forbidden artifact commit.

## 15. Risk Assessment

Data safety result:

```text
PASS: no answer loss indication in synthetic direct 100/300/600
```

Functional final-submit result:

```text
PASS: final-submit sample succeeded at all tiers
```

Performance result:

```text
NO-GO for Phase 5 rollout confidence: direct-300/600 answer latency and DB pressure are too high
```

## 16. Rollback / Cleanup Instruction

Production data cleanup is already complete for synthetic prefixes.

Fresh backup remains on VPS for rollback reference if operator needs it:

```text
backup_20260604_005915_pre_phase432f.sql.gz
```

Do not commit or export this backup.

If rollback from backup were ever needed, use the documented stop/start DB restore procedure and confirm safe window first. No rollback is currently recommended because cleanup succeeded and production health is normal.

## 17. Decision

Phase 4.3.2F execution status:

```text
completed for direct 100/300/600 functional/data validation
```

Phase 5 decision:

```text
Phase 5 remains blocked; do not propose hybrid/queue rollout yet
```

Reason:

- Direct 100/300/600 produced no HTTP failures and no consistency anomalies.
- Final-submit sample succeeded.
- However direct-300 and direct-600 show severe answer-write latency and high DB/load pressure.
- Hybrid/queue rollout should wait until the direct path has better latency headroom or a specific performance mitigation is implemented and revalidated.

Recommended next step:

```text
Phase 4.3.2G — direct answer write-path latency remediation before any Phase 5 proposal
```
