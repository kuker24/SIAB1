# Phase 4.3.2G — Direct Answer Write-Path Latency Remediation

Phase ini menindaklanjuti Phase 4.3.2F: direct 100/300/600 lulus secara fungsional/data, tetapi direct-300/direct-600 masih NO-GO untuk performa karena latency dan DB pressure sangat tinggi.

Phase ini **bukan Phase 5 rollout**, **bukan aktivasi hybrid/queue/runtime-buffer**, **bukan APK build**, dan **bukan production deploy/restart/load rerun**.

## 1. Latest Reviewed GitHub State

Baseline sebelum patch:

```text
356808b27ba06f35d0e43fd717e1d0a364a11c9c docs: record phase 4.3.2f production direct validation
```

Tidak ada commit baru di branch GitHub setelah baseline tersebut sebelum Phase 4.3.2G dimulai.

## 2. Root Cause Hypothesis

Phase 4.3.2F evidence:

| Tier | Answer p95 | Answer p99 | Answer max | DB active max | DB idle-tx max | Redis rejected/evicted |
|---|---:|---:|---:|---:|---:|---:|
| direct-100 | 492ms | 1.9s | 5.1s | 12 | 16 | 0 / 0 |
| direct-300 | 18.5s | 28.2s | 53.7s | 38 | 57 | 0 / 0 |
| direct-600 | 45.3s | 70.2s | 164.1s | 143 | 138 | 0 / 0 |

Interpretasi:

- Redis bukan bottleneck utama.
- Direct answer hot path masih melakukan DB write/transaction per answer.
- Banyak retry/autosave payload yang identik dapat memicu physical UPDATE berulang pada row yang sama.
- Progress monitor broadcast adalah non-critical side effect setelah answer commit, namun tetap memakai DB/cache/publish path pada peak mode.

## 3. Patch Summary

Runtime file changed:

```text
app/services/answer_sync_service.py
```

Patch kecil:

1. **Idempotent duplicate answer no-op update**
   - `INSERT ... ON CONFLICT DO UPDATE` sekarang memakai `where=changed_answer_payload`.
   - Physical UPDATE hanya terjadi jika payload/score berubah.
   - `answered_at` sengaja tidak dibandingkan agar retry/autosave identik tidak memaksa UPDATE.

2. **Skip non-critical progress broadcast during peak mode**
   - `_publish_progress_if_needed()` langsung return saat `EXAM_PEAK_MODE=true`.
   - Runtime answered-count Redis update tetap dilakukan sebelum fungsi ini.
   - Answer persistence sudah committed sebelum skip ini.
   - Admin/monitoring progress broadcast dianggap non-critical saat peak.

Tidak diubah:

- public endpoint path/contract;
- final-submit service;
- database schema;
- hybrid/queue/runtime-buffer flags;
- SEB/SXB/header/signature validation;
- cheating detection/emergency/admin controls;
- APK/AAB build flow.

## 4. Why Answer Safety Is Preserved

- Insert for first answer tetap berjalan seperti sebelumnya.
- Changed answer payload tetap meng-update row existing.
- Identical duplicate payload tetap mendapat response `saved`, tetapi tidak menulis row version baru.
- Unique constraint `uq_answers_session_question` tetap menjadi guard utama.
- Session lock/status recheck tetap ada sebelum write.
- Runtime answered marker tetap diperbarui best-effort setelah commit.
- Final consistency tetap harus divalidasi melalui rerun load test sebelum Phase 5.

## 5. Why Final Submit Is Preserved

- `app/services/final_submit_service.py` tidak diubah.
- Final submit tetap:
  - probe session state;
  - validate SEB;
  - flush queue/runtime buffer gates jika relevan;
  - take session advisory lock + row lock;
  - load exam/questions/options/answers;
  - grade and commit terminal state;
  - handle already-submitted idempotency.
- Answer no-op update hanya skips identical duplicate physical update; final submit still sees the persisted latest content.

## 6. Static Analyzer Result

Command:

```bash
python scripts/analyze_answer_write_path.py --format json
```

Key result after patch:

| Module | DB execute | Commits | Row locks | Advisory locks | Notes |
|---|---:|---:|---:|---:|---|
| answer sync service | 17 | 6 | 3 | 2 | counts unchanged; patch changes write/update behavior and peak side-effect guard |
| final submit service | 3 | 2 | 1 | 1 | unchanged |
| violation events | 3 | 1 | 0 | 0 | unchanged |
| admin monitoring | 30 | 5 | 0 | 0 | unchanged |

Analyzer counts do not show the expected benefit because this patch reduces physical updates and non-critical progress work rather than reducing static `execute()` markers.

## 7. Tests Run

Targeted pre-doc subset:

```bash
python -m compileall app
.venv/bin/python -m pytest tests/test_answer_sync_service_routing.py \
  tests/test_exam_write_integrity_guards.py -q
```

Result:

```text
31 passed in 0.68s
```

Full required validation:

```bash
python -m compileall app
.venv/bin/python -m pytest tests/test_runtime_policy.py \
  tests/test_answer_sync_service_routing.py \
  tests/test_answer_runtime_buffer.py \
  tests/test_final_submit_service.py \
  tests/test_exam_start_validation_cache_key.py \
  tests/test_exam_write_integrity_guards.py \
  tests/test_production_readiness_defaults.py -q
python -m py_compile scripts/analyze_answer_write_path.py
python scripts/analyze_answer_write_path.py --help
python scripts/analyze_answer_write_path.py --format json
.venv/bin/python -m pytest tests/test_analyze_answer_write_path.py -q
python -m py_compile scripts/load_test_answer_sync.py
python scripts/load_test_answer_sync.py --help
.venv/bin/python -m pytest tests/test_load_test_answer_sync.py -q
```

Results:

```text
62 passed in 0.67s
9 passed in 0.03s
32 passed in 0.05s
```

## 8. Production Action

Production action performed:

```text
no
```

No production deploy, restart, migration, code sync, or load-test rerun was performed in this remediation phase.

Fresh backup for revalidation:

```text
not created in Phase 4.3.2G because production revalidation was not approved/performed
```

## 9. Revalidation Status

Direct production-live rerun after patch:

| Tier | Status |
|---|---|
| direct-100 | not rerun after patch |
| direct-300 | not rerun after patch |
| direct-600 | not rerun after patch |
| final-submit sample | not rerun after patch |
| answer consistency | not rerun after patch |

Reason:

- user instruction requires explicit approval before production deploy/restart/migrate/revalidation after code patch;
- no such approval was requested/executed in this turn.

## 10. Expected Measurement Impact

Expected improvement areas if deployed and rerun:

- fewer physical UPDATEs/WAL churn for identical autosave/retry submissions;
- less non-critical progress publish work in `EXAM_PEAK_MODE=true`;
- lower answer p95/p99 when clients resend equivalent payloads;
- lower DB active/idle-in-transaction pressure from non-critical progress side effects.

This is **not** sufficient evidence for Phase 5 by itself. It must be measured.

## 11. Rollback Instruction

Code rollback:

```bash
git revert <phase-4.3.2g-commit-sha>
```

Operational rollback:

- no production rollback needed unless this patch is later deployed;
- if deployed and issue appears, revert code and redeploy safe-mode direct/off;
- no schema rollback required.

## 12. Decision

Phase 4.3.2G code remediation:

```text
pass pending full validation/commit
```

Phase 4.3.2G performance pass:

```text
not yet; revalidation pending
```

Phase 5:

```text
still blocked
```

Next step:

```text
Request explicit approval for deploy + fresh-backup + production-live rerun, or run equivalent isolated staging rerun, then compare direct 100/300/600 against Phase 4.3.2F baselines.
```
