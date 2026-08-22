# Phase 4.3 — P0 Direct-Path Hardening Plan

Dokumen ini mengubah temuan performance 2026-06-03 menjadi rencana patch terukur sebelum Phase 5 hybrid/queue rollout dibuka.

## Source Evidence

Production exam-day report menunjukkan bottleneck utama:

- `/api/student/exams/submit`: 1,420 requests, 616 slow >2s, avg 56.74s, max 120s, 205 5xx, 184 499.
- `/api/exams/session/{id}/status`: 244,880 requests, 63,692 499, 68,368 slow >2s, 1,246 5xx.
- Answer sync/autosave routes punya 5xx/499/slow signifikan.
- DB: 219 idle-in-transaction timeout, 297 connection closed mid-operation mentions, prepared statement missing errors.

## P0-1 Final Submit Hot Path

Goal: final submit harus menjadi jalur paling reliable dan tidak menunggu side-effect non-kritis.

Patch plan:

1. Profile transaction/query duration di final-submit service.
2. Audit query count and lock scope.
3. Pastikan commit jawaban/session terminal terjadi sebelum publish/cache/notification non-kritis.
4. Buat fast path idempotent untuk session yang sudah `submitted`/`completed`.
5. Hindari heavy recompute jika score sudah final dan request adalah retry.
6. Pastikan response final-submit tidak menunggu admin dashboard/monitoring publish.
7. Tambahkan test guard untuk retry path already-terminal.

Measurement:

- p95 final-submit direct 100/300/600.
- 5xx/499 final-submit = 0 atau tidak repeated.
- DB transaction time.
- Query count per final submit.

Rollback:

- Patch harus surgical dan bisa `git revert`.
- Tidak boleh schema change di P0 ini tanpa proposal terpisah.

## P0-2 Session Status Polling Backoff/Cache

Goal: status polling tidak mendominasi request/DB saat ujian aktif.

Patch plan:

1. Client stop polling saat session terminal.
2. Tambahkan backoff/min interval di APK/web fallback polling.
3. Prefer WebSocket event jika connected; polling hanya fallback.
4. Short TTL cache untuk status response saat status belum berubah.
5. Hindari query detail/relationship yang tidak dibutuhkan di status endpoint.
6. Normalisasi monitoring metric agar tidak per-session label explosion.

Measurement:

- Request rate `/api/exams/session/{id}/status` turun signifikan.
- 499 pada status polling turun.
- DB query count turun.
- Tidak ada regresi resume/exam status UX.

Rollback:

- Feature flag/backoff config bisa dikembalikan.
- Endpoint path tetap sama.

## P0-3 Answer Sync / Autosave De-Dup and Canonical Route

Goal: client tidak mengirim duplicate write path untuk event jawaban yang sama.

Patch plan:

1. Deteksi apakah APK/web mengirim `submit-answer`, `answer-journal/sync`, dan `auto-save-batch` secara bersamaan.
2. Tentukan canonical route per client mode:
   - APK/mobile offline-first: journal/batch sync dengan de-dup.
   - Web fallback: single answer or batch, bukan keduanya untuk event sama.
3. Tambahkan in-flight dedupe di client.
4. Tambahkan debounce/min interval aman.
5. Keep Phase 4 patch: skip DB answered-count fallback saat `EXAM_PEAK_MODE=true`.
6. Pastikan final submit tetap membaca source of truth dari DB direct writes.

Measurement:

- Total answer/autosave requests turun.
- 5xx/499 turun di answer sync endpoints.
- No answer loss indication.
- Unique answer row consistency valid.

Rollback:

- Client-side debounce/canonical route bisa revert.
- Direct DB write tetap source of truth.

## P1 DB / PgBouncer / asyncpg Audit

Goal: hilangkan idle transaction timeout dan connection closed mid-operation.

Audit plan:

1. Inspect SQLAlchemy async engine settings.
2. Confirm PgBouncer pool mode.
3. Jika transaction pooling digunakan, evaluasi asyncpg prepared statement cache behavior.
4. Audit transaction scopes di answer sync, final submit, status polling, dashboard, grading.
5. Tambah staging-first slow query/statement timeout logging.
6. Jangan ubah production DB/PgBouncer config tanpa approval eksplisit.

Measurement:

- idle-in-transaction timeout count = 0 di staging load test.
- prepared statement missing errors = 0.
- connection closed mid-operation turun.

## P1 Admin/Teacher Monitoring and Grading Throttle

Goal: monitoring/teacher/admin tidak membebani hot path siswa saat peak.

Patch plan:

1. Pertahankan `ADMIN_MONITORING_DETAIL_LEVEL=summary` saat active exam.
2. Throttle detail monitoring dan heavy dashboard endpoints.
3. Pagination/cache untuk grading/dashboard.
4. Avoid `results/all`, heavy export, template scans saat peak.
5. Admin dashboard aggregate-first dan cached.
6. Cheating detection tetap ada, tetapi async/aggregate-first.

Measurement:

- Admin/teacher endpoint p95 turun.
- Tidak ada impact ke answer/final-submit p95.
- Cheating aggregate tetap tampil di dashboard.

## Execution Order

1. Final submit idempotent fast path and profiling.
2. Session status polling backoff/cache.
3. Answer sync route de-dup/canonical route.
4. DB/PgBouncer/asyncpg audit.
5. Admin/teacher monitoring throttle.
6. Direct 100/300/600 staging validation.
7. Only then reassess Phase 5.

## Phase 5 Gate Reminder

Phase 5 remains blocked until:

- direct 100 pass;
- direct 300 pass with no significant 5xx;
- direct 600 pass with no repeated 5xx/final-submit failure;
- final-submit sample succeeds;
- answer consistency valid;
- no answer loss indication;
- hybrid10 600 503 root cause understood/mitigated;
- no production load test or production deploy involved.
