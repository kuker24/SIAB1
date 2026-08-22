# Mobile-first Answer Load Test Results — 2026-06-03

## Scope

This report summarizes a synthetic load test for the mobile-first answer hot path.
No real student accounts, sessions, answers, or tokens were used.

Target branch:

```text
review/sanitized-root-20260531-115153
```

Harness commit tested:

```text
beb08e8
```

Important caveat: a true separate staging clone was not available. Tests used a production-like VPS with synthetic-only data. Public production environment defaults were not changed. Hybrid 10% was tested through a temporary internal API container to avoid changing the public production pool.

## Synthetic dataset

- Synthetic exam: `LOADTEST_SYNTHETIC_20260603_044908`
- Synthetic exam id: `567`
- Synthetic students: `600`
- Synthetic sessions: `600`
- Synthetic questions: `40`
- Synthetic options: `160`
- CSV rows generated: `600`
- Token CSV was deleted after the test and was not committed.

## Topology observed

- Docker Compose deployment
- nginx public reverse proxy
- 8 public API containers
- 2 admin API containers
- PostgreSQL container
- Redis container
- PgBouncer container
- Celery worker/beat
- Prometheus/Grafana
- Temporary hybrid10 internal API container was removed after testing

VPS spec observed:

- 16 vCPU
- 16 GB RAM
- 58 GB root disk, about 47% used during preflight
- Linux/Ubuntu kernel 5.15

## Results summary

| Run | Requests | Success | Failures | Status counts | p50 ms | p95 ms | p99 ms | Max ms |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| smoke-direct-10 | 382 | 382 | 0 | 200=381, 204=1 | 60.45 | 78.87 | 244.21 | 267.29 |
| direct-100 | 11,377 | 11,377 | 0 | 200=11,367, 204=10 | 60.18 | 92.32 | 933.34 | 3,657.91 |
| direct-300 | 24,138 | 24,138 | 0 | 200=24,108, 204=30 | 1,455.02 | 6,539.15 | 10,617.24 | 29,228.01 |
| direct-600 | 34,745 | 34,736 | 9 | 0=9, 200=34,687, 204=49 | 6,121.89 | 25,723.38 | 38,572.30 | 82,189.41 |
| direct-final-submit-sample | 11,473 | 11,473 | 0 | 200=11,473 | 58.87 | 77.11 | 629.60 | 3,155.95 |
| hybrid10-100 | 8,471 | 8,471 | 0 | 200=8,471 | 696.87 | 1,053.26 | 2,132.01 | 2,944.36 |
| hybrid10-300 | 13,048 | 13,048 | 0 | 200=13,048 | 3,520.34 | 11,252.91 | 16,708.78 | 28,395.44 |
| hybrid10-600 | 38,894 | 38,508 | 386 | 200=38,508, 503=386 | 7,525.47 | 8,683.55 | 16,936.26 | 41,049.32 |
| hybrid10-final-submit-sample | 8,366 | 8,366 | 0 | 200=8,366 | 712.72 | 1,165.83 | 2,460.99 | 2,931.30 |

Status interpretation:

- `2xx` = success
- `0` = client timeout/exception
- `401/403` = auth/token/session problem
- `404` = route/endpoint problem
- `429` = rate-limit/pressure signal
- `5xx` = backend failure/pressure

## Final submit samples

Direct final submit sample:

- `/api/exams/submit`: 2 requests
- Success: 2/2
- Failures: 0
- p50: 151.53 ms
- p95: 163.18 ms
- max: 164.48 ms

Hybrid10 final submit sample:

- `/api/exams/submit`: 2 requests
- Success: 2/2
- Failures: 0
- p50: 147.07 ms
- p95: 182.84 ms
- max: 186.82 ms

## Redis observations

Before:

```text
pending=0
processing=0
queued_keys=0
dirty_session_keys=0
```

After direct:

```text
pending=0
processing=0
queued_keys=0
dirty_session_keys=0
```

After hybrid10 failure:

```text
pending=0
processing=0
queued_keys=0
dirty_session_keys=0
```

Redis did not show queue backlog. Pressure appears to be in app/DB/write-path concurrency rather than un-drained Redis pending buffers.

## PostgreSQL counters

Before:

```text
answers: inserts=5854 updates=18616
exam_sessions: inserts=670 updates=363
exam_logs: inserts=0 updates=0
```

After direct:

```text
answers: inserts=6454 updates=100030
exam_sessions: inserts=670 updates=365
exam_logs: inserts=0 updates=0
```

After hybrid10:

```text
answers: inserts=6454 updates=159967
exam_sessions: inserts=670 updates=457
exam_logs: inserts=0 updates=0
```

Approximate deltas:

- Direct phase: `answers +600 inserts`, `answers +81,414 updates`, `exam_sessions +2 updates`
- Hybrid10 phase after direct: `answers +0 inserts`, `answers +59,937 updates`, `exam_sessions +92 updates`

## Integrity check

Minimal synthetic integrity check:

```text
600/600 synthetic sessions had answer_count=1
zero_answer_sessions=0
```

Hybrid10 final submit sample submitted 2 synthetic sessions, both with answer_count=1.

## Admin / cheating monitoring notes

- `/health` remained HTTP 200 after tests.
- `/admin/monitoring` unauthenticated page check returned HTTP 200 quickly.
- Production nginx still has emergency marker `EMERGENCY_TRAFFIC_SHED_LOG_VIOLATION_20260602`, so direct log-violation calls through nginx returned 204.
- Hybrid internal app log-violation calls returned 200.
- This means production cheating event persistence remains affected by the emergency nginx shed and should be restored only in a safe window after approval.

## Gate decision

Hybrid 10% did **not** pass the 600 VU gate.

Reasons:

- `hybrid10-600` produced 386 HTTP 503 responses on `/api/exams/submit-answer`.
- p95/p99 latency remains high.
- Direct 600 also showed pressure with 9 client timeout/exception failures and p95 around 25.7 seconds.

Hybrid 50% was **not run** because hybrid 10% failed.

Hybrid 100% was **not run**.

## Conclusion

Do not claim production-ready based on this run.

Recommended next steps:

1. Build a true staging clone with the same API worker topology as production.
2. Re-run direct and hybrid with apples-to-apples routing/topology.
3. Investigate direct 600 timeout exceptions.
4. Investigate hybrid10 600 HTTP 503 responses.
5. Restore production log-violation emergency shed only after a safe window and explicit approval.
6. Do not proceed to hybrid 50% until hybrid 10% passes 600 VU with zero answer loss, stable Redis pending/dirty counts, and no repeated 503s.

## Rollback / cleanup performed

- Public production env was not changed.
- Temporary hybrid10 containers were removed.
- Redis pending/processing/dirty keys were 0 after hybrid failure.
- Token CSV and temporary env files were deleted from host/container.
- No APK/AAB/keystore/env/token/CSV files were committed.
