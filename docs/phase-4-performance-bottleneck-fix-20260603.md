# Phase 4 — Performance Bottleneck Fix (2026-06-03)

Dokumen ini adalah rencana dan catatan eksekusi awal Phase 4 untuk meningkatkan stabilitas direct mode pada jalur jawaban dan final submit. Semua pekerjaan dilakukan di local branch untuk review GitHub terlebih dahulu. Tidak ada deploy VPS, restart service production, migration production, APK build, atau load test production.

## Tujuan Phase 4

1. Meningkatkan stabilitas backend direct mode untuk 300–600 peserta concurrent.
2. Menurunkan DB pressure dan write amplification pada answer hot path.
3. Menjaga final submit sebagai jalur prioritas tertinggi.
4. Menjaga keamanan jawaban siswa tanpa mengubah public endpoint contract.
5. Mempertahankan admin dashboard dan cheating detection sebagai aggregate-first/async/non-blocking.
6. Menyediakan peta bottleneck dan patch kecil yang reversible sebelum local/staging load test berikutnya.

## Problem Statement dari Load Test Sebelumnya

Hasil load test synthetic sebelumnya menunjukkan:

- Direct mode 100/300/600 sudah pernah dijalankan.
- Direct 600 menunjukkan pressure berat dan client timeout/exception pada sebagian kecil request.
- Hybrid10 600 menghasilkan banyak HTTP 503.
- Redis backlog tetap 0, sehingga Redis queue bukan bottleneck dominan pada run tersebut.
- Final submit sample pada direct dan hybrid10 sukses, sehingga final submit harus tetap diprioritaskan dan tidak dibuat risky.
- Bottleneck paling mungkin berada pada app/DB/write-path concurrency, terutama round trip database, commit per answer, locking, dan monitoring fallback.

Kesimpulan operasional: belum layak klaim production-ready untuk hybrid rollout. Fokus Phase 4 adalah direct-mode-first.

## Non-Goals

Phase 4 ini **tidak** melakukan:

- Aktivasi hybrid/queue/runtime buffer.
- Build APK atau upload APK/AAB.
- Deploy/restart/recreate service VPS.
- Load test production.
- Migration/schema change production.
- Rewrite total `app/api/exams.py` atau pembuatan microservice baru.
- Perubahan public endpoint path/contract.
- Pelemahan APK signature/header/SXB/SEB validation.
- Penghapusan cheating detection, emergency exit, atau admin command.
- Export raw answer/PII.

## Production Baseline yang Harus Tetap Aman

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

## Direct-Mode-First Strategy

1. Pertahankan direct DB write sebagai sumber kebenaran jawaban.
2. Optimasi hal non-kritis di sekitar answer save, bukan mengganti model penyimpanan.
3. Hindari tambahan write/log/dashboard detail pada path submit-answer.
4. Gunakan Redis/cache untuk monitoring/progress bila tersedia; hindari DB fallback non-kritis saat peak.
5. Pastikan final submit tetap melakukan flush/check yang diperlukan dan memiliki handling transient DB pressure dengan `503 Retry-After`.
6. Uji perubahan kecil lewat unit/regression test sebelum local/staging load test.

## Hot Path yang Dianalisis

| Area | File/Endpoint | Fokus Review |
|---|---|---|
| Single answer | `POST /api/exams/submit-answer`, `app/services/answer_sync_service.py` | session probe, validation cache, row lock, upsert, commit, Redis marker, progress broadcast |
| Auto-save legacy | `app/services/answer_sync_service.py` | Redis-only answer marker, no direct answer write |
| Auto-save batch | `app/services/answer_sync_service.py` | batch dedupe, valid question check, one commit per batch, conflict retry |
| Answer journal/sync | `app/services/answer_sync_service.py` | event idempotency, latest-by-question, one transaction per sync |
| Final submit | `app/services/final_submit_service.py` | idempotency, buffer/queue flush gates, grading, logs, final commit, Retry-After 503 |
| Violation logging | `app/api/violation_events.py`, `app/services/violation_event_service.py` | async enabled by default, avoid blocking answer path |
| Admin dashboard | `app/api/monitoring.py`, `app/core/violations_dashboard.py` | summary/aggregate-first, detail lazy/on-demand |
| Heavy exports | `app/api/exam_exports.py` | disabled during peak through `heavy_exports_active` |

## Static Review Findings

Static helper: `scripts/analyze_answer_write_path.py`.

Summary local source scan:

| Module | DB execute markers | Commit markers | Lock markers | Hot risk |
|---|---:|---:|---:|---|
| answer sync service | 17 | 6 | 5 | single-answer has commit/upsert/lock per answer; progress DB fallback can add pressure |
| final submit service | 3 | 2 | 2 | final submit loads session/questions/options/answers and writes score logs; must remain priority |
| violation events | 3 | 1 | 0 | safe if async stays enabled; sync fallback is write-heavy |
| admin monitoring | 30 | 5 | 0 | must remain summary/aggregate-first during peak |
| heavy exports | 5 | 0 | 0 | guarded by heavy export flag; keep disabled during peak |

## Risk Areas

1. **Commit per answer**: single answer direct path commits each answer write.
2. **Repeated SELECT per answer**: session probe, question validation fallback, lock/load, progress fallback.
3. **Session lock serialization**: advisory lock and row lock preserve correctness but serialize bursts per session.
4. **Session/progress update amplification**: Redis marker and progress broadcast after each saved answer can add pressure if fallback reads DB.
5. **Non-critical log writes**: final submit writes logs; keep only critical logs on submit path.
6. **Final submit contention**: burst submit loads questions/options/answers and writes score/session/log rows.
7. **Admin dashboard queries**: detail views and recovery/admin actions can add load if used during peak.
8. **DB pool/PgBouncer saturation**: direct 600 pressure points toward connection/transaction throughput limits.
9. **Violation sync fallback**: if `VIOLATION_ASYNC_ENABLED=false`, violation endpoint becomes write-heavy.

## Optimization Candidates

### Candidate 1 — Skip non-critical progress DB fallback during peak

Status: implemented as a small runtime patch.

Change: in `AnswerSyncService._publish_progress_if_needed`, when `EXAM_PEAK_MODE=true` and Redis/runtime answered-count is unavailable, skip DB `COUNT(DISTINCT answers.question_id)` fallback and do not publish that non-critical progress update.

Why safe:

- Answer is already persisted before progress publish.
- Public response contract remains unchanged.
- Final submit is unaffected.
- Monitoring progress may be temporarily less granular only if Redis/runtime count is unavailable during peak.
- Avoids extra DB query and commit for non-critical monitoring under pressure.

### Candidate 2 — Keep validation Redis/cache-first

Status: documented for next review.

Question validation already uses cached payload. Future work should measure cache misses and avoid per-answer DB fallback when possible.

### Candidate 3 — Prefer batch/journal paths where clients already support them

Status: documented.

Batch autosave and journal sync commit once per batch/sync and reduce write amplification compared to single-answer per click. Do not change endpoint contracts; only prefer existing batch/journal clients in controlled UX.

### Candidate 4 — Final submit log pressure review

Status: no runtime change in this pass.

`EXAM_SUBMITTED` and `SCORE_BREAKDOWN` logs are useful audit artifacts. Removing/defering them is risky until Phase 3 audit requirements and grading/reporting dependencies are reviewed.

### Candidate 5 — Index/schema proposal only if metrics prove need

Status: not implemented.

Any new index/schema work must be proposed separately, tested in staging, and never deployed to production without safe-window approval.

## Test Plan Local/Staging

### Unit/regression

```bash
python -m py_compile scripts/analyze_answer_write_path.py
python scripts/analyze_answer_write_path.py --help
python -m compileall app
pytest tests/test_runtime_policy.py \
       tests/test_answer_sync_service_routing.py \
       tests/test_answer_runtime_buffer.py \
       tests/test_final_submit_service.py \
       tests/test_exam_start_validation_cache_key.py \
       tests/test_exam_write_integrity_guards.py \
       tests/test_production_readiness_defaults.py -q
```

### Static/source review

```bash
python scripts/analyze_answer_write_path.py
python scripts/analyze_answer_write_path.py --format json
```

### Load test after patch

Local/staging only:

1. Direct 100 synthetic.
2. Direct 300 synthetic.
3. Direct 600 synthetic.
4. Final submit sample under each tier.
5. Optional dashboard summary monitoring only.

No production load test.

## Acceptance Criteria

- No production deploy/restart/migration/load test.
- No APK build/upload.
- No public endpoint contract change.
- No hybrid/queue/runtime buffer activation.
- Direct mode remains default.
- Final submit tests pass.
- No answer loss in synthetic local/staging checks.
- No 5xx regression in local/staging load test compared to previous direct run.
- Admin dashboard remains summary/aggregate-first during peak.
- Violation async remains enabled by default.
- Forbidden/sensitive files are not committed.

## Rollback Plan

Runtime patch rollback is small and reversible:

1. Revert the change in `AnswerSyncService._publish_progress_if_needed` that skips progress DB fallback during `EXAM_PEAK_MODE=true`.
2. Re-run the Phase 4 pytest subset.
3. Push revert for review.
4. No production action is needed unless the reviewed patch has later been deployed.

## Current Phase 4 Status

- Direct-mode bottlenecks are mapped.
- Static analysis helper added.
- Safe-mode default guard strengthened for admin monitoring summary mode.
- One monitoring-only runtime optimization implemented.
- Ready for GitHub review and then local/staging direct load test.

## Phase 5 Gate

Do **not** proceed to hybrid rollout until direct 300/600 local/staging tests pass the stability gate and direct-mode bottlenecks are understood. Hybrid10 previously failed at 600 with 503, so hybrid50/100 remains blocked.
