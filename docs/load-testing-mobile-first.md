# Mobile-first load testing runbook

Tujuan runbook ini adalah memberi bukti staging bahwa optimasi mobile-first menurunkan DB pressure tanpa mengorbankan jawaban siswa. Jangan jalankan traffic ke production tanpa approval operator eksplisit.

## Guardrail wajib

- Gunakan data staging/synthetic saja; jangan pakai token, akun, atau session siswa asli.
- Jangan menjalankan test di `man1rokanhulu.cloud` saat ujian aktif.
- Jangan langsung menguji 100% queue/buffer di production.
- Final submit tetap prioritas; hentikan test jika 503 final submit naik atau ada indikasi answer loss.
- Script default adalah dry-run; traffic HTTP hanya dikirim jika `--execute` dipakai.

## Env stage

### Baseline direct

```env
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
```

### Hybrid 10% canary

```env
ANSWER_WRITE_MODE=hybrid
ANSWER_QUEUE_ENABLED=true
ANSWER_QUEUE_PERCENTAGE=10
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
```

### Hybrid 50% canary

```env
ANSWER_WRITE_MODE=hybrid
ANSWER_QUEUE_ENABLED=true
ANSWER_QUEUE_PERCENTAGE=50
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
```

Naik ke 50% hanya jika 10% stabil.

## Virtual users dan urutan evidence

Untuk evidence 300-600 concurrent yang realistis, wajib gunakan CSV multi-session synthetic. Jalankan bertahap:

1. Baseline direct 100 VU selama 3-5 menit.
2. Baseline direct 300 VU selama 5-10 menit.
3. Baseline direct 600 VU selama 10-15 menit.
4. Hybrid 10% 100 VU selama 3-5 menit.
5. Hybrid 10% 300 VU selama 5-10 menit.
6. Hybrid 10% 600 VU selama 10-15 menit.
7. Hybrid 50% hanya jika hybrid 10% stabil.

Setiap stage wajib menyertakan:

- answer submit/autosave traffic,
- journal sync bila tersedia di harness,
- violation burst ringan,
- final submit sample kecil bila session staging boleh ditutup,
- admin monitoring summary tetap terbuka di satu browser/admin session.

## Script smoke/load helper

Script aman tersedia di:

```bash
scripts/load_test_answer_sync.py
```

Script punya dua mode:

1. **Single-session smoke** — berguna untuk cek konektivitas, contract endpoint, dan worst-case lock contention pada satu session. Ini **bukan** bukti 300-600 peserta karena semua VU menabrak session lock yang sama.
2. **Multi-session CSV** — mode yang wajib untuk evidence VPS/staging 300-600 concurrent karena setiap VU dibagi round-robin ke synthetic session berbeda.

### Single-session smoke dry-run

```bash
python scripts/load_test_answer_sync.py \
  --base-url https://staging.example.test \
  --session-id 1001 \
  --question-id 2001 \
  --vus 10 \
  --duration-seconds 60
```

### Single-session smoke execute

```bash
python scripts/load_test_answer_sync.py \
  --base-url https://staging.example.test \
  --token "$STAGING_TEST_TOKEN" \
  --session-id 1001 \
  --question-id 2001 \
  --selected-option-id 3001 \
  --vus 10 \
  --duration-seconds 60 \
  --summary-json results-smoke.json \
  --execute
```

## CSV multi-session synthetic

CSV minimal:

```csv
session_id,question_id,selected_option_id,token
1001,2001,3001,eyJ...
1002,2002,3002,eyJ...
1003,2003,3003,eyJ...
```

Rules:

- `session_id` dan `question_id` wajib.
- `selected_option_id` boleh kosong; fallback ke `--selected-option-id`.
- `token` boleh kosong; fallback ke `--token` global.
- Worker memilih row CSV dengan round-robin: `rows[worker_id % len(rows)]`.
- Jangan memakai data/token siswa asli.

### Multi-session staging command

```bash
python scripts/load_test_answer_sync.py \
  --base-url https://staging.example.test \
  --sessions-csv staging_sessions.csv \
  --vus 100 \
  --duration-seconds 180 \
  --include-violation-burst \
  --summary-json results-direct-100.json \
  --execute
```

Jika token tidak disimpan di CSV, gunakan fallback token staging:

```bash
python scripts/load_test_answer_sync.py \
  --base-url https://staging.example.test \
  --token "$STAGING_TEST_TOKEN" \
  --sessions-csv staging_sessions.csv \
  --vus 300 \
  --duration-seconds 300 \
  --include-violation-burst \
  --summary-json results-direct-300.json \
  --execute
```

Final submit sample bersifat experimental/staging-only dan default `0`:

```bash
python scripts/load_test_answer_sync.py \
  --base-url https://staging.example.test \
  --sessions-csv staging_sessions.csv \
  --vus 100 \
  --duration-seconds 180 \
  --final-submit-sample-rate 0.02 \
  --summary-json results-submit-sample.json \
  --execute
```

Gunakan final submit sample hanya pada session synthetic yang memang boleh ditutup.

Script menolak host production yang dikenal kecuali diberi `--allow-production`; flag itu tetap membutuhkan approval operator terpisah.

## Metrik yang harus dicatat

Untuk setiap stage catat:

| Metrik | Target awal |
| --- | --- |
| p50 latency `/api/exams/submit-answer` | stabil/turun vs baseline |
| p95 latency `/api/exams/submit-answer` | tidak naik tajam |
| p99 latency `/api/exams/submit-answer` | tidak ada spike berkepanjangan |
| final submit success rate | 100% pada sample test |
| 429 rate | terukur dan tidak massal; ini pressure signal, bukan success |
| 503 rate | 0 atau sangat rendah; investigasi jika muncul |
| Redis pending/processing queue size | tidak naik terus-menerus |
| Redis dirty session count | tidak naik terus-menerus |
| DB writes/minute | turun pada hybrid vs direct |
| DB CPU/connection count | stabil dan tidak mendekati limit |
| answer loss | 0 |

Summary JSON script menyimpan:

- total requests,
- success/failures (`success` hanya HTTP 2xx; 401/403/404/429/5xx dihitung sebagai failure),
- status counts untuk investigasi auth/session/rate-limit/backend pressure,
- p50/p95/p99/max,
- per endpoint summary,
- VU count,
- duration,
- `sessions_csv_used`,
- `unique_sessions_count`.

## Redis/DB observation contoh

Jalankan hanya di staging/VPS test yang disetujui.

Redis queue/runtime metrics:

```bash
redis-cli LLEN runtime:answer_queue:pending
redis-cli LLEN runtime:answer_queue:processing
redis-cli --scan --pattern 'runtime:answer_queue:queued:*' | wc -l
redis-cli --scan --pattern 'runtime:session:*:dirty_questions' | wc -l
```

Catatan:

- Jangan gunakan `KEYS` di production karena bisa memblokir Redis.
- Gunakan `--scan` untuk menghitung pattern key secara incremental.

DB connection sample:

```sql
SELECT state, count(*)
FROM pg_stat_activity
WHERE datname = 'exam_system'
GROUP BY state;
```

DB write pressure sample:

```sql
SELECT relname, n_tup_ins, n_tup_upd, n_tup_del
FROM pg_stat_user_tables
WHERE relname IN ('answers', 'exam_sessions', 'exam_logs')
ORDER BY relname;
```

## Pass/fail criteria

Pass:

- Answer loss = 0.
- Final submit sample sukses 100%.
- Redis pending/processing queue tidak tumbuh tanpa drain.
- Dirty buffer/session count turun setelah drain/final submit.
- p95/p99 tidak lebih buruk dari baseline direct secara signifikan.
- DB connection count dan CPU lebih stabil pada hybrid canary.

Fail/stop:

- Ada jawaban hilang atau mismatch saat final submit.
- 503 final submit muncul berulang.
- Redis dirty/pending/processing terus naik.
- DB connection mendekati limit.
- Admin monitoring mengganggu answer/final-submit path.

## Rollback env

Rollback total:

```env
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
```

Graceful drain rollback jika masih ada dirty buffer:

```env
ANSWER_WRITE_MODE=hybrid
ANSWER_QUEUE_ENABLED=true
ANSWER_QUEUE_PERCENTAGE=0
```

Setelah pending/dirty buffer kosong, pindahkan ke rollback total.
