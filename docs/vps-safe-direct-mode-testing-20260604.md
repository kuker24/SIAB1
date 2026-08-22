# Phase 4.3.2A — VPS-Safe Direct-Mode Testing Preparation

Dokumen ini mencatat persiapan aman untuk direct-mode execution validation setelah VPS dapat diakses kembali.

## Scope

Phase 4.3.2A hanya melakukan:

- read-only VPS safety checks;
- target classification;
- tooling readiness verification;
- blocker documentation for direct-mode execution validation.

Phase ini **bukan** production load test dan **bukan** production rollout.

## Latest Reviewed GitHub State

Latest reviewed branch head before this check:

```text
87483333994639ff0c09506a852cc0429a177db2 docs: record vps access restart and testing status
```

No new GitHub commit was found after that baseline before this Phase 4.3.2A work started.

## Operator Approval Status

Operator approved:

- VPS access for preparation/verification;
- prior VPS restart, already completed and documented separately;
- publishing progress/status to GitHub.

Operator has **not** approved:

- production live load test;
- creating/recreating containers;
- migration;
- deploy/code sync;
- APK build/upload;
- hybrid/queue/runtime-buffer rollout.

## VPS Read-Only Safety Check

Check time:

```text
Thu Jun 4 00:22:32 WIB 2026
```

System aggregate:

| Metric | Value |
|---|---:|
| Uptime | 16 min |
| Load average | 0.18 / 0.28 / 0.35 |
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

Container health:

- 8 public API containers: healthy.
- 2 admin API containers: healthy.
- Nginx: healthy.
- PostgreSQL: healthy.
- PgBouncer: healthy.
- Redis: healthy.
- Celery worker/beat: healthy.
- Prometheus/Grafana: healthy.

Nginx local health checks:

| Attempt | HTTP | Time |
|---:|---:|---:|
| 1 | 200 | 0.021995s |
| 2 | 200 | 0.019836s |
| 3 | 200 | 0.018538s |

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
| `used_memory_human` | 14.04M |
| `maxmemory_human` | 1.37G |
| Keyspace DB0 | 1,780 keys |
| Keyspace DB1 | 21,884 keys |

## Safe-Mode Environment Verification

API container env sample confirms safe-mode remains active:

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

No hybrid/queue/runtime-buffer rollout was activated.

## Target Classification

Current VPS target classification:

```text
Production live stack only
```

Evidence:

- Only production `ujian_online-*` containers were found.
- Only production public Nginx ports 80/443 were exposed.
- PostgreSQL non-template databases visible: `exam_system`, `postgres`.
- No separate staging API service/port was found.
- No separate staging database/schema was verified.
- No separate staging Redis namespace/DB policy was verified.

Decision:

- Direct 100/300/600 **must not** run against this production live stack.
- Phase 4.3.2 remains blocked until an isolated staging/non-production target exists.

## Tooling Readiness

### Controlled local environment

Commands run locally:

```bash
python -m py_compile scripts/load_test_answer_sync.py
python scripts/load_test_answer_sync.py --help
.venv/bin/python -m pytest tests/test_load_test_answer_sync.py -q
```

Result:

```text
32 passed in 0.03s
```

Local tooling is ready.

### VPS `/root/ujian_online` environment

Commands attempted on VPS without traffic:

```bash
python3 -m py_compile scripts/load_test_answer_sync.py
python3 scripts/load_test_answer_sync.py --help
```

Result:

| Check | Result |
|---|---|
| Python executable | `python3` only; `python` not available |
| `py_compile` | pass |
| `--help` | fail |

Observed blocker:

```text
ModuleNotFoundError: No module named 'httpx'
```

Interpretation:

- The VPS production tree/tooling is not ready for Phase 4.3.2 execution.
- The deployed helper appears to require `httpx` at import-time or lacks the latest lazy-import guardrail behavior.
- No package install, code sync, or deploy was performed because that would be a production change requiring explicit approval.

## Synthetic Dataset / CSV Status

Synthetic sessions CSV status:

```text
/tmp/ujianonline-direct-sessions-20260604.csv: not created
```

Reason:

- No isolated staging/non-production target exists yet.
- Creating synthetic write data against the production live DB is not allowed for direct 100/300/600 validation.

## Dry-Run Status

CSV dry-run status: **not executed**.

Reason:

- No valid isolated target.
- No synthetic sessions CSV.
- VPS helper `--help` currently fails due missing `httpx`/tooling mismatch.

## Direct Execution Status

| Tier | Status | Reason |
|---|---|---|
| direct-100 | not executed | only production live stack exists; no synthetic CSV; VPS helper not ready |
| direct-300 | not executed | direct-100 not executed/pass |
| direct-600 | not executed | direct-300 not executed/pass |

No production load test was run.

## Final-Submit Sample Status

Status: **not executed**.

Expected endpoint for future valid isolated run:

```text
/api/student/exams/submit
```

No token/session/answer payload was sent.

## Answer Consistency Status

Status: **not executed**.

Reason:

- no synthetic direct-mode execution;
- no non-production DB target;
- no synthetic session ID set.

## DB / PgBouncer Notes

Production DB/PgBouncer were only checked using aggregate read-only probes.

Observed production aggregate was stable at check time:

- active queries over 5s: 0;
- idle-in-transaction sessions: 0;
- active connection count: 1;
- PgBouncer container healthy.

No raw SQL containing PII/answer content was exported.

## Redis Notes

Production Redis was only checked using aggregate `INFO` metrics.

Observed:

- rejected connections: 0;
- evicted keys: 0;
- memory usage low versus maxmemory;
- Redis container healthy.

No raw Redis keys or token/session values were exported.

## What Was Not Done

- No restart/reboot in this Phase 4.3.2A check.
- No deploy.
- No code sync.
- No package install on VPS.
- No migration.
- No container recreate.
- No APK/AAB build/upload.
- No production live load test.
- No synthetic production write load.
- No raw answer/token/session/PII export.
- No hybrid/queue/runtime-buffer activation.
- No synthetic CSV committed.
- No summary JSON committed.

## Requirements Before Phase 4.3.2B

Before direct execution validation can start safely:

1. Provision or identify an isolated staging/non-production stack on VPS or elsewhere.
2. Ensure it has a separate API target/port not routed to production live public domain.
3. Ensure it uses a separate non-production DB/schema with no real student data.
4. Ensure it uses separate Redis DB/namespace.
5. Sync or run the latest load-test helper in a controlled environment without changing production runtime.
6. Verify `python scripts/load_test_answer_sync.py --help` works in the execution environment.
7. Generate `/tmp/ujianonline-direct-sessions-20260604.csv` with synthetic-only session/question/option/token values.
8. Run dry-run first.
9. Execute direct-100 only after target and CSV are verified.
10. Escalate to direct-300/direct-600 only after prior tier and consistency checks pass.

## Current Decision

- VPS access: confirmed.
- VPS production health: healthy at read-only check time.
- Current target classification: **production live stack only**.
- Phase 4.3.2A: **continue / blocked by missing isolated staging target and synthetic CSV**.
- Phase 4.3.2 direct validation: **not passed**.
- Phase 5: **still blocked**.
