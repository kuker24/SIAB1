# Phase 4.2 — Direct-Mode Local/Staging Load Test Validation (2026-06-03)

## Ringkasan

Dokumen ini mencatat validasi Phase 4.2 untuk direct-mode setelah patch Phase 4.

- Commit runtime patch yang divalidasi: `d175db2b74fff49f49291f8400fbd5623f8f468b`
- Commit Phase 4.1 tooling/docs terakhir saat validasi: `31fb952`
- Environment: local workspace only; **bukan production**
- Production touched: **no**
- VPS deploy/restart/migration: **no**
- Production load test: **no**
- APK build/upload: **no**
- Dataset: synthetic only required, tetapi **tidak tersedia di environment lokal ini**

## Safe-Mode yang Dipersyaratkan

```text
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

Phase 4.2 tidak mengubah runtime code dan tidak mengaktifkan hybrid/queue/runtime buffer.

## Preflight Environment

| Check | Result |
|---|---|
| Target host production-like (`103.175.218.56`, `man1rokanhulu.cloud`, `adminujian`) | Not used |
| Local API `http://127.0.0.1:8000/health` | No response in this workspace |
| Docker availability | `docker` unavailable |
| Synthetic sessions CSV | Not found |
| Load-test execute allowed? | **No — blocked by missing local/staging target and synthetic dataset** |
| Load-test script dry-run | Pass using `http://127.0.0.1:8000` without `--execute` |

Dry-run command executed:

```bash
.venv/bin/python scripts/load_test_answer_sync.py \
  --base-url http://127.0.0.1:8000 \
  --session-id 1 \
  --question-id 1 \
  --selected-option-id 1 \
  --vus 1 \
  --duration-seconds 1 \
  --final-submit-sample-rate 0.0
```

Dry-run result:

```text
Plan:
  base_url=http://127.0.0.1:8000
  vus=1 duration_seconds=1
  sessions_csv_used=False unique_sessions=1
  endpoint=/api/exams/submit-answer
  first_token=<empty>
Dry-run only. Add --execute with staging token/session/question IDs to send traffic.
```

## Local Validation Tests

Commands executed locally:

```bash
python -m py_compile scripts/analyze_answer_write_path.py
.venv/bin/python scripts/analyze_answer_write_path.py --help
.venv/bin/python scripts/analyze_answer_write_path.py --format json
python -m compileall app
.venv/bin/python -m pytest tests/test_analyze_answer_write_path.py \
       tests/test_answer_sync_service_routing.py \
       tests/test_runtime_policy.py \
       tests/test_answer_runtime_buffer.py \
       tests/test_final_submit_service.py \
       tests/test_exam_start_validation_cache_key.py \
       tests/test_exam_write_integrity_guards.py \
       tests/test_production_readiness_defaults.py -q
```

Result:

```text
68 passed in 0.90s
```

## Static Analyzer Summary

Output dipadatkan dari `scripts/analyze_answer_write_path.py --format json`:

| Module | DB execute markers | Commit markers | Row lock markers | Advisory lock markers | Notes |
|---|---:|---:|---:|---:|---|
| single/batch/journal answer sync | 17 | 6 | 3 | 2 | Main direct answer write-path; Phase 4 skipped non-critical progress DB fallback during peak/cache miss |
| answer sync route | 0 | 0 | 0 | 0 | Route wrapper only |
| legacy answer sync route | 2 | 0 | 0 | 0 | Legacy route has DB reads but no commit marker |
| final submit | 3 | 2 | 1 | 1 | Final submit unchanged and remains priority path |
| violation events | 3 | 1 | 0 | 0 | Keep `VIOLATION_ASYNC_ENABLED=true` during peak |
| admin monitoring | 30 | 5 | 0 | 0 | Keep dashboard summary-only during active exam |
| heavy exports | 5 | 0 | 0 | 0 | Keep disabled during peak |

## Test 100

```text
submit-answer total: Not executed
submit-answer 2xx: Not executed
submit-answer 4xx: Not executed
submit-answer 429: Not executed
submit-answer 5xx: Not executed
client timeout/exception: Not executed
p50/p95/p99 jika tersedia: Not executed
final submit sample count: Not executed
final submit success: Not executed
DB/PgBouncer notes: Not executed; no local/staging DB target available
Redis notes: Not executed; no local/staging Redis target available
Answer consistency check: Not executed
Conclusion: Blocked before execute; missing local/staging API and synthetic sessions CSV
```

## Test 300

```text
submit-answer total: Not executed
submit-answer 2xx: Not executed
submit-answer 4xx: Not executed
submit-answer 429: Not executed
submit-answer 5xx: Not executed
client timeout/exception: Not executed
p50/p95/p99 jika tersedia: Not executed
final submit sample count: Not executed
final submit success: Not executed
DB/PgBouncer notes: Not executed
Redis notes: Not executed
Answer consistency check: Not executed
Conclusion: Not executed because 100-user execute gate was not available
```

## Test 600

```text
submit-answer total: Not executed
submit-answer 2xx: Not executed
submit-answer 4xx: Not executed
submit-answer 429: Not executed
submit-answer 5xx: Not executed
client timeout/exception: Not executed
p50/p95/p99 jika tersedia: Not executed
final submit sample count: Not executed
final submit success: Not executed
DB/PgBouncer notes: Not executed
Redis notes: Not executed
Answer consistency check: Not executed
Conclusion: Not executed because 100/300 execute gates were not available
```

## Overall Decision

```text
GO/NO-GO Phase 5: NO-GO
```

Reason:

- Local validation tests passed.
- Load-test script dry-run passed.
- However direct 100/300/600 execute tests were **not executed** because this workspace has no local/staging API target, no Docker runtime, and no synthetic sessions CSV.
- Therefore the main direct-mode performance gate remains pending.

## Root Cause Notes

Execution blocked by environment, not by code failure:

1. `http://127.0.0.1:8000/health` did not respond.
2. Docker is unavailable, so local compose stack cannot be checked or started from this workspace.
3. No synthetic sessions CSV was found locally.
4. Production hosts are explicitly forbidden for load test execution.

## Required Follow-Up

Before Phase 5 can open, run direct-mode load validation in a real non-production target:

1. Provision local/staging API + PostgreSQL + Redis.
2. Create synthetic-only exam/users/sessions/questions/options.
3. Export synthetic sessions CSV with staging-only tokens; do not commit it.
4. Run direct 100.
5. If pass, run direct 300.
6. If pass, run direct 600.
7. Record final-submit sample results for each tier.
8. Verify answer consistency.
9. Keep dashboard summary-only and heavy export disabled.
10. Keep queue/hybrid/runtime buffer off.

## Suggested Non-Production Commands

Adjust file paths to staging synthetic CSVs only:

```bash
.venv/bin/python scripts/load_test_answer_sync.py \
  --base-url http://127.0.0.1:8000 \
  --sessions-csv /path/to/synthetic_sessions_100.csv \
  --vus 100 \
  --duration-seconds 300 \
  --summary-json /tmp/phase4-direct-100-summary.json \
  --final-submit-sample-rate 0.05 \
  --execute

.venv/bin/python scripts/load_test_answer_sync.py \
  --base-url http://127.0.0.1:8000 \
  --sessions-csv /path/to/synthetic_sessions_300.csv \
  --vus 300 \
  --duration-seconds 300 \
  --summary-json /tmp/phase4-direct-300-summary.json \
  --final-submit-sample-rate 0.05 \
  --execute

.venv/bin/python scripts/load_test_answer_sync.py \
  --base-url http://127.0.0.1:8000 \
  --sessions-csv /path/to/synthetic_sessions_600.csv \
  --vus 600 \
  --duration-seconds 300 \
  --summary-json /tmp/phase4-direct-600-summary.json \
  --final-submit-sample-rate 0.05 \
  --execute
```

Do not use production URL. Do not commit raw CSV/JSON summaries unless sanitized and approved.

## Phase 5 Gate

Phase 5 remains blocked until all are true:

- Direct 100 pass.
- Direct 300 pass with no significant 5xx.
- Direct 600 pass with no repeated 5xx/final-submit failure.
- Final submit sample succeeds.
- Answer consistency is valid.
- No answer loss indication.
- Hybrid10 600 503 root cause is understood or mitigated.

## Superseding Execution Evidence — Phase 4.3.2F Production-Live Direct Validation (2026-06-04)

Operator explicitly approved controlled production-live direct-mode validation after a fresh backup.
See full sanitized report:

```text
docs/phase-4.3.2f-fresh-backup-production-live-validation-20260604.md
```

Fresh backup gate:

| Item | Result |
|---|---|
| Fresh backup | `backup_20260604_005915_pre_phase432f.sql.gz` |
| Timestamp | 2026-06-04 00:59:20 WIB |
| Size | 11,892,705 bytes |
| Integrity | `gzip -t`: pass |
| Backup committed/exported | no |

Production preflight:

| Check | Result |
|---|---:|
| Active published exam windows | 0 |
| In-progress sessions before synthetic data | 0 |
| Safe-mode direct/off | pass |
| API/DB/PgBouncer/Redis/Nginx health | healthy |

Direct-mode execution summary:

| Tier | Requests | Failures | Status | Answer p95 | Answer p99 | Answer max | Final submit | Consistency |
|---|---:|---:|---|---:|---:|---:|---|---|
| direct-100 | 10,224 | 0 | all 200 | 492.22ms | 1,903.34ms | 5,109.23ms | 2/2 success | valid |
| direct-300 | 10,999 | 0 | all 200 | 18,498.30ms | 28,242.70ms | 53,663.94ms | 6/6 success | valid |
| direct-600 | 11,033 | 0 | all 200 | 45,344.45ms | 70,218.83ms | 164,139.81ms | 6/6 success | valid |

DB/Redis observation:

| Tier | Load1 max | DB active max | DB idle-tx max | DB active >5s max | Redis rejected | Redis evicted |
|---|---:|---:|---:|---:|---:|---:|
| direct-100 | 10.63 | 12 | 16 | 0 | 0 | 0 |
| direct-300 | 11.93 | 38 | 57 | 0 | 0 | 0 |
| direct-600 | 57.56 | 143 | 138 | 1 | 0 | 0 |

Cleanup:

- Synthetic users/sessions/exam/questions/options/answers were deleted by exact prefix.
- Remaining synthetic users: 0.
- Remaining synthetic exams: 0.
- Global in-progress sessions after cleanup: 0.
- Temporary CSV/summary JSON/token artifacts under `/tmp` were deleted after sanitized extraction.

Updated Phase 5 decision:

```text
NO-GO / blocked
```

Reason:

- Functional/data integrity passed: no HTTP failures, final-submit samples succeeded, and answer consistency was valid through direct-600.
- Performance confidence did **not** pass: direct-300 and direct-600 answer-write latency and DB/load pressure were too high for rollout confidence.
- Do not start Phase 5 or enable hybrid/queue/runtime-buffer until direct answer-write latency is remediated and revalidated.
