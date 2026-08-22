# Phase 4.3 — Non-Production Direct-Mode Load Test Enablement

Phase 4.3 menyiapkan target non-production, data sintetis, dan guardrail agar validasi direct 100/300/600 bisa benar-benar dieksekusi tanpa menyentuh production.

## Objective

1. Menyiapkan local/staging target yang cukup mirip production untuk uji direct-mode.
2. Menyiapkan synthetic sessions CSV untuk `scripts/load_test_answer_sync.py` tanpa data siswa asli.
3. Menjalankan direct 100 → 300 → 600 hanya di local/staging.
4. Merekam final-submit sample dan answer consistency.
5. Menjaga Phase 5 tetap blocked sampai semua gate direct-mode terbukti pass.

## Safety Boundaries

Production forbidden actions:

- Tidak deploy/restart/recreate/migrate VPS production.
- Tidak load test production.
- Tidak memakai akun/token/session/jawaban siswa asli.
- Tidak export raw answer/PII/token.
- Tidak build APK/AAB.
- Tidak aktifkan hybrid/queue/runtime buffer.
- Tidak mengubah DB schema.
- Tidak mengubah public endpoint contract.

Production-like host harus selalu ditolak oleh tooling Phase 4.3/4.3.1:

- `103.175.218.56`
- `man1rokanhulu.cloud`
- `adminujian`

`--allow-production` tidak tersedia di load-test helper. Jika operator mencoba flag lama itu, argparse harus menolak. Tidak ada production override untuk Phase 4.

## Required Safe-Mode Environment

Target local/staging untuk direct-mode validation harus memakai deklarasi berikut:

```env
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
EXAM_PEAK_MODE=true
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
MOBILE_APK_PRIMARY=true
APK_BUILD_ENDPOINT_ENABLED=false
SEB_DESKTOP_LEGACY_ENABLED=false
SEB_QR_ENABLED=false
SEB_DEBUG_ENDPOINTS_ENABLED=false
HEAVY_EXPORT_ENABLED=false
```

Queue/hybrid/runtime buffer tidak boleh aktif selama Phase 4.3.

## Local/Staging Target Requirements

Minimum target:

- API FastAPI berjalan.
- PostgreSQL non-production berjalan.
- Redis non-production berjalan.
- PgBouncer optional tetapi direkomendasikan untuk staging parity.
- Dataset sintetis dengan exam, questions, options, users, sessions.
- Tidak ada data siswa asli.
- Domain/base URL bukan production-like host.
- Sessions CSV dan summary output wajib berada di absolute path bawah `/tmp`.

Recommended staging parity:

- API replicas minimal 2 jika ingin cek pooling/concurrency.
- PgBouncer enabled jika production memakai PgBouncer.
- `EXAM_PEAK_MODE=true` untuk mencerminkan hot-path patch Phase 4.

## Synthetic Sessions CSV Rules

CSV untuk load script harus berisi:

```csv
session_id,question_id,selected_option_id,token
```

Rules:

- Hanya untuk local/staging.
- Tidak memakai session/token real student.
- Jangan commit CSV.
- Simpan di absolute path bawah `/tmp`, misalnya `/tmp/ujianonline-direct-sessions-20260603.csv`; relative path atau path repo harus ditolak tooling.
- Token boleh berada di CSV hanya untuk local/staging dan tetap tidak boleh dipush.
- Jika token tidak di CSV, gunakan fallback `--token` hanya di shell lokal yang aman.
- Hapus CSV setelah validasi selesai.

## Direct 100/300/600 Execution Plan

Run order:

1. Dry-run:

```bash
python scripts/load_test_answer_sync.py \
  --base-url http://127.0.0.1:8000 \
  --sessions-csv /tmp/ujianonline-direct-sessions.csv \
  --vus 100 \
  --duration-seconds 60 \
  --summary-json /tmp/ujianonline-direct-100-summary.json
```

2. Execute direct 100:

```bash
python scripts/load_test_answer_sync.py \
  --base-url http://127.0.0.1:8000 \
  --sessions-csv /tmp/ujianonline-direct-sessions.csv \
  --vus 100 \
  --duration-seconds 180 \
  --final-submit-sample-rate 0.02 \
  --final-submit-endpoint /api/student/exams/submit \
  --summary-json /tmp/ujianonline-direct-100-summary.json \
  --execute
```

3. Execute direct 300 only if direct 100 pass.
4. Execute direct 600 only if direct 300 pass.

Suggested durations:

| Tier | VUs | Duration | Final Submit Sample |
|---|---:|---:|---:|
| direct-100 | 100 | 180s | 2% |
| direct-300 | 300 | 300s | 1–2% |
| direct-600 | 600 | 300–600s | 1% |

## Final-Submit Sample Procedure

For every tier:

1. Use only synthetic sessions.
2. Enable `--final-submit-sample-rate` low enough to avoid submitting all synthetic sessions too early.
3. Default final-submit sample endpoint adalah `/api/student/exams/submit` agar menguji hotspot APK/mobile dari laporan production. Jika local/staging hanya mengekspos alias lama `/api/exams/submit`, override boleh digunakan hanya untuk membuktikan alias compatibility, bukan sebagai bukti utama APK/mobile.
4. Verify all final-submit samples return 2xx.
5. Retry already-submitted synthetic sessions to confirm idempotent fast path where applicable.
6. Record latency p50/p95/p99 and failures.

Any repeated 5xx or 499 on final submit is a NO-GO.

## Answer Consistency Validation Procedure

After each tier, run SELECT-only checks against non-production DB:

```sql
SELECT COUNT(*) AS answer_rows FROM answers WHERE session_id IN (...synthetic sessions...);
SELECT session_id, COUNT(DISTINCT question_id) AS answered_questions
FROM answers
WHERE session_id IN (...synthetic sessions...)
GROUP BY session_id;
SELECT status, COUNT(*) FROM exam_sessions
WHERE id IN (...synthetic sessions...)
GROUP BY status;
```

Expected:

- No duplicate answer rows beyond unique `(session_id, question_id)` behavior.
- Answer rows exist for submitted payloads.
- Final-submit sampled sessions become terminal.
- No score/terminal anomalies for final-submit sample.

Do not export raw answers/options/token.

## Evidence to Record

For each tier:

- Base URL class: local or staging, not production.
- Safe-mode env snapshot with secrets redacted.
- VUs, duration, think time, final-submit endpoint, CSV row count, unique session count.
- Request count, success/failure, status counts.
- p50/p95/p99/max latency overall and per endpoint.
- Final-submit sample result.
- Answer consistency result.
- DB notes: active connections, idle-in-transaction timeout count, long queries.
- PgBouncer notes if enabled.
- Redis notes: rejected connections, evicted keys, ops/sec.
- Cleanup status.

## NO-GO Conditions

Phase 5 remains blocked if any of these occur:

- Direct 100 not executed or fails.
- Direct 300 not executed or has significant repeated 5xx.
- Direct 600 not executed or has repeated 5xx/final-submit failure.
- Final-submit sample fails.
- Answer consistency invalid.
- Any answer loss indication.
- Production host used or old production override attempted.
- Real student data used.
- Queue/hybrid/runtime buffer enabled.
- DB/PgBouncer unstable under direct load.
- Hybrid10 600 503 root cause still not understood/mitigated.

## Rollback / No-Op Instructions

Phase 4.3 should be no-op for production.

Local/staging cleanup:

1. Stop load test process.
2. Delete synthetic sessions CSV from `/tmp`.
3. Delete summary JSON from `/tmp` after extracting sanitized numbers.
4. Remove synthetic users/sessions/exams from non-production DB only.
5. Flush only synthetic Redis keys if created.
6. Do not touch production.

## Current Decision

As of this document, direct 100/300/600 has not yet been executed in local/staging. Phase 5 remains **BLOCKED**.
