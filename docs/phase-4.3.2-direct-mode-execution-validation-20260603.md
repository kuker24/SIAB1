# Phase 4.3.2 — Direct-Mode Execution Validation

Dokumen ini mencatat status eksekusi Phase 4.3.2 setelah guardrail load-test helper Phase 4.3.1 dinyatakan pass.

## Scope

Phase 4.3.2 bertujuan menjalankan direct-mode validation 100 → 300 → 600 terhadap target **local/staging only**.

Phase ini bukan production rollout.

## Safety Boundaries

Status safety pada attempt ini:

- Production touched: **no**.
- VPS deploy/restart/recreate/migration: **no**.
- Production load test: **no**.
- APK build/upload: **no**.
- Runtime `app/` code change: **no**.
- DB schema change: **no**.
- Endpoint contract change: **no**.
- Hybrid/queue/runtime buffer activation: **no**.
- Raw answer/PII/token/session export: **no**.
- Synthetic sessions CSV committed: **no**.
- Summary JSON committed: **no**.

## Latest Git State

Latest reviewed baseline before Phase 4.3.2:

```text
f86aa5d93281dbe2970f608c42e29e5f97f95304 test: harden phase 4.3 load test guardrails
```

No new GitHub commit was found after that baseline before this Phase 4.3.2 note was created.

## Tooling Readiness

Commands run locally:

```bash
python -m py_compile scripts/load_test_answer_sync.py
python scripts/load_test_answer_sync.py --help
.venv/bin/python -m pytest tests/test_load_test_answer_sync.py -q
```

Result:

```text
32 passed in 0.04s
```

Tooling guardrails verified from Phase 4.3.1 remain in force:

- dry-run default;
- production-like host rejection;
- no `--allow-production` override;
- `--sessions-csv` absolute `/tmp` path requirement;
- `--summary-json` absolute `/tmp` path requirement;
- final-submit default endpoint `/api/student/exams/submit`;
- token masking;
- direct-mode only declaration;
- queue disabled;
- runtime buffer disabled.

## Local/Staging Target Verification

Target verification result:

| Check | Result |
|---|---|
| Docker CLI available | **no** (`docker CLI not available`) |
| Local API `http://127.0.0.1:8000/health` | **unavailable** (`Connection refused`) |
| Local API `http://localhost:8000/health` | **unavailable** (`Connection refused`) |
| Synthetic sessions CSV `/tmp/ujianonline-direct-sessions-20260603.csv` | **missing** |
| Synthetic sessions CSV `/tmp/ujianonline-direct-sessions.csv` | **missing** |
| PostgreSQL non-production verified | **not verified** |
| Redis non-production verified | **not verified** |
| PgBouncer non-production verified | **not verified** |
| Safe-mode env on target verified | **not verified** |

Decision: target is not ready. Direct 100/300/600 execution is blocked.

## Dry-Run Guardrail Check

A non-traffic dry-run was executed with a single synthetic placeholder session/question ID:

```bash
python scripts/load_test_answer_sync.py \
  --base-url http://127.0.0.1:8000 \
  --session-id 1001 \
  --question-id 2001 \
  --vus 1 \
  --duration-seconds 1 \
  --final-submit-sample-rate 1.0 \
  --summary-json /tmp/ujianonline-direct-dryrun-432.json
```

Observed plan output confirmed:

```text
endpoint=/api/exams/submit-answer
endpoint=/api/student/exams/submit (experimental final-submit sample)
safety_policy=direct_mode queue_disabled runtime_buffer_disabled
Dry-run only. Add --execute with staging token/session/question IDs to send traffic.
```

No summary JSON was created during dry-run.

## Execution Results

| Tier | Status | Reason |
|---|---|---|
| direct-100 | **not executed** | no local/staging API target and no synthetic sessions CSV |
| direct-300 | **not executed** | direct-100 did not execute/pass |
| direct-600 | **not executed** | direct-300 did not execute/pass |

## Final-Submit Sample Result

Status: **not executed**.

Reason:

- no local/staging API target;
- no synthetic sessions CSV;
- no synthetic tokens/sessions;
- execution would be invalid without target verification.

Expected endpoint for future valid run:

```text
/api/student/exams/submit
```

## Answer Consistency Result

Status: **not executed**.

Reason:

- no synthetic sessions were executed;
- no non-production DB target was verified;
- no SELECT-only consistency check could be run safely.

## DB / PgBouncer Notes

Status: **not available**.

No non-production DB/PgBouncer target was verified, so no DB/PgBouncer metrics were collected.

No production DB was touched.

## Redis Notes

Status: **not available**.

No non-production Redis target was verified, so no Redis metrics were collected.

No production Redis was touched.

## Phase 4.3.2 Gate Decision

Phase 4.3.2 does **not** pass yet.

Blocking reasons:

1. No local/staging API target available.
2. Docker CLI unavailable in current environment.
3. No synthetic sessions CSV under `/tmp`.
4. Safe-mode env on target could not be verified.
5. direct-100 was not executed.
6. direct-300 was not executed.
7. direct-600 was not executed.
8. Final-submit sample was not executed.
9. Answer consistency was not executed.

## Next Required Actions

Before Phase 4.3.2 can pass:

1. Provision local/staging API + PostgreSQL + Redis.
2. Verify safe-mode env direct/off on target.
3. Create 600+ synthetic users/sessions/questions/options.
4. Generate `/tmp/ujianonline-direct-sessions-20260603.csv` with synthetic-only session/question/option/token values.
5. Run dry-run with the CSV.
6. Execute direct-100.
7. Run answer consistency SELECT-only checks.
8. Execute direct-300 only if direct-100 passes.
9. Execute direct-600 only if direct-300 passes.
10. Record sanitized aggregate results only.

## Current Decision

- Phase 4.3.2: **continue / blocked by missing non-production target and CSV**.
- Phase 5: **still BLOCKED**.

Do not propose opening Phase 5 until direct 100/300/600, final-submit sample, answer consistency, DB/PgBouncer, and Redis gates are actually evidenced on local/staging.
