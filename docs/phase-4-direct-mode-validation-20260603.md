# Phase 4.1 — Direct Mode Validation Plan (2026-06-03)

Dokumen ini melengkapi Phase 4 setelah patch awal:

- Commit runtime patch yang divalidasi: `d175db2b74fff49f49291f8400fbd5623f8f468b`
- Commit message: `perf: reduce direct answer write-path pressure`

Phase 4.1 hanya menambah validasi, test tooling, dan checklist local/staging. Dokumen ini tidak mengotorisasi perubahan production.

## Scope Validasi

Scope validasi:

- Local/GitHub review only.
- Tidak deploy VPS.
- Tidak restart service production.
- Tidak run load test production.
- Tidak run migration production.
- Tidak build APK.
- Tidak upload APK/AAB.
- Tidak mengubah DB schema.
- Tidak mengubah public endpoint contract.
- Tidak mengaktifkan hybrid/queue/runtime buffer.
- Tidak export raw answer/PII.

## Ringkasan Patch Runtime Phase 4

Patch runtime di `app/services/answer_sync_service.py`:

- `_publish_progress_if_needed()` tetap publish progress jika runtime/Redis answered-count tersedia.
- Jika `EXAM_PEAK_MODE=true` dan runtime/Redis answered-count tidak tersedia, fungsi skip DB fallback `COUNT(DISTINCT answers.question_id)` untuk progress monitoring.
- Jawaban sudah tersimpan sebelum progress publish.
- Final submit tidak berubah.
- Endpoint contract tidak berubah.

Tujuan patch: mengurangi DB pressure non-kritis di answer hot path saat peak mode.

## Safe-Mode Baseline yang Harus Tetap Terjaga

```text
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
EXAM_PEAK_MODE=true saat ujian/peak
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
MOBILE_APK_PRIMARY=true
SEB_DESKTOP_LEGACY_ENABLED=false
SEB_QR_ENABLED=false
SEB_DEBUG_ENDPOINTS_ENABLED=false
APK_BUILD_ENDPOINT_ENABLED=false
TELEGRAM_ALERTING_ENABLED=false
HEAVY_EXPORT_ENABLED=false saat peak
```

## Command Validasi Lokal

Command yang harus dijalankan sebelum review/merge:

```bash
python -m py_compile scripts/analyze_answer_write_path.py
python scripts/analyze_answer_write_path.py --help
python scripts/analyze_answer_write_path.py --format json
python -m compileall app
pytest tests/test_analyze_answer_write_path.py \
       tests/test_answer_sync_service_routing.py \
       tests/test_runtime_policy.py \
       tests/test_answer_runtime_buffer.py \
       tests/test_final_submit_service.py \
       tests/test_exam_start_validation_cache_key.py \
       tests/test_exam_write_integrity_guards.py \
       tests/test_production_readiness_defaults.py -q
```

Jika `pytest` global tidak tersedia, gunakan virtualenv repo:

```bash
.venv/bin/python -m pytest tests/test_analyze_answer_write_path.py \
       tests/test_answer_sync_service_routing.py \
       tests/test_runtime_policy.py \
       tests/test_answer_runtime_buffer.py \
       tests/test_final_submit_service.py \
       tests/test_exam_start_validation_cache_key.py \
       tests/test_exam_write_integrity_guards.py \
       tests/test_production_readiness_defaults.py -q
```

Status validasi lokal Phase 4.1: **executed locally** menggunakan virtualenv repo.

Hasil ringkas:

- `python -m py_compile scripts/analyze_answer_write_path.py tests/test_analyze_answer_write_path.py`: pass.
- `python scripts/analyze_answer_write_path.py --help`: pass.
- `python scripts/analyze_answer_write_path.py --format json`: pass, JSON valid.
- `python -m compileall app`: pass.
- `.venv/bin/python -m pytest tests/test_analyze_answer_write_path.py -q`: 9 passed.
- `.venv/bin/python -m pytest tests/test_answer_sync_service_routing.py tests/test_production_readiness_defaults.py -q`: 24 passed.
- `.venv/bin/python -m pytest tests/test_analyze_answer_write_path.py tests/test_answer_sync_service_routing.py tests/test_runtime_policy.py tests/test_answer_runtime_buffer.py tests/test_final_submit_service.py tests/test_exam_start_validation_cache_key.py tests/test_exam_write_integrity_guards.py tests/test_production_readiness_defaults.py -q`: 68 passed.

## Static Analyzer Output Summary

Helper: `scripts/analyze_answer_write_path.py`.

Ringkasan output lokal sebelumnya, dipadatkan agar tidak terlalu panjang:

| Module | DB execute markers | Commit markers | Lock markers | Risk summary |
|---|---:|---:|---:|---|
| answer sync service | 17 | 6 | 5 | direct answer path masih punya DB write/commit dan lock per answer; progress DB fallback sudah dikurangi saat peak |
| final submit service | 3 | 2 | 2 | final submit tetap prioritas; grading/log writes harus dijaga dan diuji dalam submit wave |
| violation events | 3 | 1 | 0 | aman jika `VIOLATION_ASYNC_ENABLED=true`; sync fallback tetap risk saat peak |
| admin monitoring | 30 | 5 | 0 | harus tetap summary/aggregate-first saat peak |
| heavy exports | 5 | 0 | 0 | harus tetap disabled saat peak |

Analyzer bersifat static/source-only:

- Tidak connect ke DB.
- Tidak butuh real student data.
- Tidak membutuhkan `.env`.
- Tidak membaca/menulis APK, DB dump, SQL dump, SQLite/DB, atau data siswa.
- Menolak root production-like (`103.175.218.56`, `man1rokanhulu.cloud`, `adminujian`).

## Local/Staging Direct-Mode Load Test Plan

Load test berikut hanya boleh dilakukan di local/staging, bukan production.

### Environment

- Mode: direct.
- `ANSWER_WRITE_MODE=direct`.
- `ANSWER_QUEUE_ENABLED=false`.
- `ANSWER_QUEUE_PERCENTAGE=0`.
- `EXAM_PEAK_MODE=true` untuk simulasi peak.
- `VIOLATION_ASYNC_ENABLED=true`.
- `ADMIN_MONITORING_DETAIL_LEVEL=summary`.
- `HEAVY_EXPORT_ENABLED=false`.

### Test Matrix

1. Direct 100 synthetic users.
2. Direct 300 synthetic users.
3. Direct 600 synthetic users.
4. Final-submit sample pada setiap tier.
5. Dashboard summary only.
6. Optional light violation burst hanya jika async path aktif dan bukan production.

### Metrics

Catat:

- submit-answer total.
- submit-answer 2xx.
- submit-answer 4xx/429.
- submit-answer 5xx.
- client timeout/exception/status 0.
- p50/p95/p99 jika tersedia.
- final submit sample count.
- final submit success/failure.
- DB/PgBouncer notes.
- Redis backlog/dirty notes.
- answer row consistency check.

## Gate sebelum Phase 5

Phase 5 hybrid rollout tetap blocked sampai direct-mode validation pass.

Minimum gate:

1. Direct 100 synthetic pass tanpa 5xx regression.
2. Direct 300 tidak boleh ada 5xx signifikan.
3. Direct 600 tidak boleh ada repeated 5xx atau final-submit failure.
4. Final submit sample berhasil.
5. Answer row consistency valid.
6. Redis backlog boleh dipantau, tetapi queue/hybrid tetap off.
7. Admin dashboard summary-only tidak menambah pressure signifikan.
8. Tidak ada production action selama validasi.

## Decision

Current decision:

- Phase 4 siap menuju local/staging direct-mode load test setelah Phase 4.1 tests pass.
- Phase 5 hybrid rollout masih **blocked**.
- Hybrid50/100 tidak boleh dimulai sampai direct 100/300/600 local/staging pass dan hybrid10 600 503 root cause sudah dipahami.

## Rollback

Jika patch runtime Phase 4 perlu dibatalkan sebelum deploy review:

```bash
git revert d175db2b74fff49f49291f8400fbd5623f8f468b
```

Jika Phase 4.1 docs/tests perlu dibatalkan:

```bash
git revert <phase-4.1-commit>
```

Tidak ada rollback production karena dokumen/test ini tidak melakukan production action.
