# Synthetic Load-Test Data Generation Guide

Panduan ini menjelaskan cara menyiapkan data sintetis untuk load test direct-mode tanpa data siswa asli dan tanpa menyentuh production.

## Non-Negotiable Rules

- Jangan gunakan akun siswa/guru/admin asli.
- Jangan gunakan session/token asli.
- Jangan export raw answer, PII, token production, atau question key.
- Jangan commit CSV sessions, token, DB dump, SQL dump, SQLite DB, atau summary JSON yang sensitif.
- Output CSV wajib memakai absolute path di bawah `/tmp`; path repo/relative harus ditolak.
- Target hanya local/staging.
- Production-like host harus selalu ditolak: `103.175.218.56`, `man1rokanhulu.cloud`, `adminujian`.
- Tidak ada `--allow-production` untuk Phase 4 load-test helper.
- Default semua helper harus dry-run; DB write butuh `--execute` jika tool write dibuat.

## Synthetic Dataset Strategy

Buat data non-production yang cukup realistis:

| Entity | Minimum |
|---|---:|
| Synthetic users | 600–700 |
| Synthetic exam | 1–3 |
| Questions per exam | 40 |
| Options per multiple-choice question | 4–5 |
| Exam sessions | 600+ |
| Session status before load | `in_progress` |
| Token | local/staging JWT only |

Naming convention yang aman:

- Exam title prefix: `LOADTEST_SYNTHETIC_DIRECT_YYYYMMDD`
- Username prefix: `loadtest_student_YYYYMMDD_0001`
- Class prefix: `LOADTEST_X`
- No real names, no real NISN, no real class roster.

## CSV Format

`scripts/load_test_answer_sync.py` expects:

```csv
session_id,question_id,selected_option_id,token
1001,2001,3001,local_or_staging_token
```

Rules:

- `session_id`: synthetic `exam_sessions.id`.
- `question_id`: synthetic `questions.id` belonging to same exam.
- `selected_option_id`: synthetic `question_options.id` belonging to the question.
- `token`: JWT for the synthetic user/session target only.

If tokens are not written into CSV, pass a fallback token only for a single-user smoke. For realistic 300–600 VU, use per-row synthetic tokens. Dry-run output must show only masked token values.

## Safe Output Paths

Recommended:

```text
/tmp/ujianonline-direct-sessions-20260603.csv
/tmp/ujianonline-direct-100-summary.json
/tmp/ujianonline-direct-300-summary.json
/tmp/ujianonline-direct-600-summary.json
```

Never use:

```text
sessions.csv
docs/*sessions*.csv
reports/*sessions*.csv
static/*
flutter_client_code/*
/home/user/repo/*sessions*.csv
```

## Data Generation Procedure

1. Start local/staging stack.
2. Confirm target is not production-like.
3. Confirm env is direct/off:

```env
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
EXAM_PEAK_MODE=true
APK_BUILD_ENDPOINT_ENABLED=false
```

4. Create synthetic exam/questions/options using existing non-production admin/import tooling or a staging-only SQL/script approved for that environment.
5. Create 600+ synthetic users and sessions.
6. Generate local/staging JWT tokens for synthetic users.
7. Write CSV to `/tmp` only.
8. Run load script dry-run first.
9. Keep final-submit sample endpoint default `/api/student/exams/submit` to exercise the APK/mobile hotspot. Use `/api/exams/submit` only as an explicit compatibility override if local/staging does not expose the student path yet.
10. Execute direct 100 → 300 → 600 only after prior tier passes.
11. Run answer consistency SELECT-only checks.
12. Cleanup synthetic data in non-production.

## Cleanup Instructions

Non-production cleanup should remove only records with the synthetic prefix/date:

- synthetic answers;
- synthetic exam logs;
- synthetic exam sessions;
- synthetic questions/options;
- synthetic exams;
- synthetic users;
- synthetic Redis keys if any.

Do not run cleanup against production. Keep cleanup SQL/script scoped by synthetic prefix and date.

## Validation Checklist

Before execution:

- [ ] Target is local/staging.
- [ ] Base URL is not production-like.
- [ ] Safe-mode direct/off confirmed.
- [ ] CSV is an absolute path under `/tmp`.
- [ ] CSV not tracked by git.
- [ ] No real user/session/token/answer data.
- [ ] Dry-run output masks token.
- [ ] `--summary-json` points to absolute path under `/tmp`.
- [ ] Final-submit sample endpoint is `/api/student/exams/submit` unless explicitly documenting alias compatibility.
- [ ] `--execute` only after operator confirms staging/local target.

After execution:

- [ ] 2xx-only success counted as success.
- [ ] 4xx/429/5xx counted as failure.
- [ ] Final-submit sample recorded.
- [ ] Answer consistency valid.
- [ ] DB/PgBouncer stable.
- [ ] Redis no rejected/evicted issue.
- [ ] CSV/summary artifacts removed or retained only locally.

## Current Tooling Note

`scripts/load_test_answer_sync.py` already supports:

- dry-run by default;
- production host rejection with no Phase 4 production override;
- per-row session/question/option/token CSV;
- final-submit sample defaulting to `/api/student/exams/submit`;
- 2xx-only success criteria;
- token masking in dry-run output;
- `/tmp`-only sessions CSV and summary JSON guard;
- direct-mode safety declaration guard.

A DB-writing synthetic generator is intentionally not added in this phase until a confirmed local/staging DB target and exact cleanup policy are available.
