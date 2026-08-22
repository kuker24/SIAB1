# Production Exam-Day Performance Report — 2026-06-03

Laporan ini adalah hasil pemeriksaan **read-only** terhadap VPS production pada malam 2026-06-03 setelah hari ujian. Tujuannya mencatat gejala lambat/error yang terjadi hari ini dan daftar kandidat patch berikutnya.

## Batasan dan Keamanan

- Production action: **read-only only**.
- Tidak ada deploy.
- Tidak ada restart/recreate container.
- Tidak ada migration.
- Tidak ada load test production.
- Tidak ada APK build/upload.
- Tidak ada perubahan konfigurasi.
- Tidak ada export raw answer, token, atau PII.
- IP disajikan hanya dalam bentuk masked/aggregate bila diperlukan.
- Endpoint dengan session id dinormalisasi menjadi `{id}` di ringkasan.

## Waktu Pemeriksaan

- Host: `adminujian`
- Tanggal pemeriksaan: 2026-06-03 malam, sekitar 22:48–22:55 WIB.
- Rentang log: sejak `2026-06-03 00:00:00 +07`.
- Branch lokal saat laporan dibuat: `review/sanitized-root-20260531-115153`
- Commit lokal saat laporan dibuat: `b806048`.

## Executive Summary

Sistem **tidak terlihat crash** saat dicek malam hari:

- Load average rendah: `0.18, 0.52, 0.54`.
- RAM available sekitar `8.1GiB`.
- Disk root 47% used.
- Semua container utama healthy.
- Saat dicek, tidak ada ujian aktif dan tidak ada session `in_progress`.

Namun sepanjang hari ujian, log menunjukkan pressure nyata:

1. **Request volume tinggi**: sekitar `572,691` request sejak tengah malam WIB.
2. **Client cancel tinggi (`499`)**: `124,522` request, dominan pada session status polling dan autosave/sync.
3. **5xx signifikan**: sekitar `9,673` response 5xx, terutama autosave/sync, WebSocket, session status, health, dan final submit.
4. **Slow request besar** pada answer sync, autosave batch, final submit, join/start exam, auth refresh, dan status polling.
5. **DB idle-in-transaction timeout**: `219` kejadian, plus `ConnectionDoesNotExistError`/prepared statement errors yang mengindikasikan connection/pool/transaction pressure.
6. **Data completion aggregate bagus**: semua session hari ini yang tercatat pada query aggregate berstatus `submitted`, semua memiliki score; `SESSION_START` = `SCORE_BREAKDOWN` = `863`, dengan `754 EXAM_SUBMITTED` dan `109 EXAM_AUTO_SUBMITTED_TIMEOUT`.
7. Tidak ada security event yang tercatat hari ini pada query aggregate.

Kesimpulan: masalah utama hari ini lebih mengarah ke **application/DB write-path dan polling pressure**, bukan DDoS tunggal atau server down total.

## System Snapshot Saat Dicek

| Area | Status |
|---|---|
| Uptime | 23 hari lebih |
| Logged-in shell user | 0 saat snapshot `who/w` |
| Load average | `0.18, 0.52, 0.54` |
| RAM | 15GiB total, 8.1GiB available |
| Disk `/` | 47% used |
| Redis rejected connections | 0 |
| Redis evicted keys | 0 |
| Redis ops/sec saat snapshot | 39 |
| Answer queue key sample | kosong/tidak terlihat backlog key |
| DB long active query saat snapshot | 0 |

Container utama healthy saat snapshot:

- nginx
- api-api8
- api_admin/api_admin2
- celery_worker/celery_beat
- postgres
- pgbouncer
- redis
- prometheus/grafana

## Jadwal dan Sesi Ujian Hari Ini

Query aggregate DB menunjukkan exam window hari ini mencakup Ekonomi, Bahasa Inggris, PKN, Sosiologi, dan beberapa draft/template malam.

### Session Status Hari Ini

| Exam | Status | Sessions | Score Present |
|---|---:|---:|---:|
| UJIAN SUMATIF AKHIR EKONOMI kelas X | submitted | 32 | 32 |
| ASA SEMESTER GENAP EKONOMI KELAS XI | submitted | 130 | 130 |
| ASA SEMESTER GENAP PKN KELAS XI | submitted | 130 | 130 |
| ASA Bahasa Inggris XI | submitted | 130 | 130 |
| ASA BAHASA INGGRIS X | submitted | 155 | 155 |
| UAS GENAP EKONOMI KELAS X | submitted | 94 | 94 |
| ASA SOSIOLOGI KELAS X | submitted | 155 | 155 |
| UJIAN SUMATIF AKHIR EKONOMI kelas XD | submitted | 30 | 30 |
| Ujian Ke II Bahasa Inggris X/XI | submitted | 5 | 5 |
| Template AKHLAK V2 records | submitted | 2 | 2 |

Total session dari event log:

| Event | Count |
|---|---:|
| SESSION_START | 863 |
| SCORE_BREAKDOWN | 863 |
| EXAM_SUBMITTED | 754 |
| EXAM_AUTO_SUBMITTED_TIMEOUT | 109 |

Catatan: secara aggregate, session completion hari ini tampak lengkap karena `SESSION_START` dan `SCORE_BREAKDOWN` sama-sama `863`. Ada `109` auto-submit timeout yang perlu direview dari sisi UX/koneksi/performa, tetapi tidak menunjukkan missing grading aggregate.

## Traffic Nginx Hari Ini

Total request sejak tengah malam WIB: `572,691`.

### Status Code Summary

| Status | Count | Notes |
|---:|---:|---|
| 200 | 410,077 | mayoritas berhasil |
| 499 | 124,522 | client closed request; sangat tinggi |
| 401 | 6,467 | auth/session expired/unauthorized |
| 502 | 5,745 | upstream error/bad gateway |
| 503 | 3,402 | service unavailable/upstream pressure |
| 101 | 2,400 | WebSocket upgrade |
| 404 | 1,116 | not found/noise/client old path |
| 403 | 785 | forbidden/access control |
| 504 | 307 | gateway timeout |
| 500 | 219 | application error |
| 429 | 25 | rate limit kecil, bukan penyebab utama |

Approximate 5xx total: `9,673` (`502 + 503 + 504 + 500`).

## Top Endpoint Pressure

Normalized top paths:

| Path | Requests |
|---|---:|
| `/api/exams/session/{id}/status` | 244,880 |
| `/api/exams/submit-answer` | 84,196 |
| `/api/exams/answer-journal/sync` | 61,665 |
| `/api/exams/auto-save-batch` | 34,950 |
| `/api/student/exams/auto-save-batch` | 31,438 |
| `/ws/exam/{exam}/{session}` | 10,117 |
| `/api/student/exams/join` | 3,099 |
| `/api/student/exams/{exam}/start` | 2,705 |
| `/api/auth/refresh` | 2,064 |
| `/api/student/auth/refresh` | 1,802 |
| `/api/student/exams/submit` | 1,420 |

Interpretasi:

- Polling status per session adalah traffic terbesar dan kandidat optimasi paling kuat.
- Sistem menjalankan beberapa jalur answer sync sekaligus: `submit-answer`, `answer-journal/sync`, `auto-save-batch`, dan `student/exams/auto-save-batch`. Ini kemungkinan menambah write/read pressure dan perlu disederhanakan/debounce lebih lanjut.

## 5xx Hotspots

Normalized top 5xx paths:

| Path | 5xx Count |
|---|---:|
| `/ws/exam/{exam}/{session}` | 2,208 |
| `/api/student/exams/auto-save-batch` | 1,782 |
| `/api/exams/auto-save-batch` | 1,735 |
| `/api/exams/session/{id}/status` | 1,246 |
| `/api/exams/answer-journal/sync` | 1,199 |
| `/health` | 421 |
| `/api/student/exams/submit` | 205 |
| `/api/student/auth/refresh` | 133 |
| `/api/student/exams/{exam}/start` | 50 |
| `/api/auth/refresh` | 49 |
| `/api/student/exams/join` | 47 |

Catatan:

- 5xx pada WebSocket perlu dipisahkan dari durasi normal WebSocket. Tetapi 5xx WebSocket tetap perlu dicek reconnect/backoff dan upstream closure.
- 5xx pada `/api/student/exams/submit` adalah prioritas tinggi karena final submit adalah jalur paling penting.
- 5xx `/health` menunjukkan saat peak beberapa upstream/health request ikut terdampak.

## Client Cancel / 499 Hotspots

Normalized top 499 paths:

| Path | 499 Count |
|---|---:|
| `/api/exams/session/{id}/status` | 63,692 |
| `/api/student/exams/auto-save-batch` | 22,114 |
| `/api/exams/answer-journal/sync` | 18,990 |
| `/api/auth/refresh` | 1,150 |
| `/api/student/exams/{exam}/start` | 484 |
| `/api/student/exams/join` | 304 |
| `/api/teacher/grading/grade-essay` | 202 |
| `/api/student/exams/submit` | 184 |

Interpretasi:

- 499 tinggi biasanya berarti client/browser/APK menutup koneksi sebelum server selesai. Pada hari ujian ini kemungkinan karena request terlalu lama, client timeout, jaringan siswa, atau tab/app retry/reconnect.
- Dominasi status polling dan autosave/sync memperkuat dugaan bottleneck bukan dari satu endpoint saja, tetapi dari kombinasi polling + sync + DB pressure.

## Slow Request Hotspots

Normalized non-WebSocket slow requests (`rt >= 2s`):

| Path | Slow Count | Avg RT | Max RT |
|---|---:|---:|---:|
| `/api/exams/session/{id}/status` | 68,368 | 4.91s | 60.00s |
| `/api/student/exams/auto-save-batch` | 25,795 | 13.90s | 300.00s |
| `/api/exams/answer-journal/sync` | 25,767 | 8.52s | 336.67s |
| `/api/exams/auto-save-batch` | 10,844 | 33.18s | 120.10s |
| `/api/student/exams/join` | 1,651 | 7.42s | 120.01s |
| `/api/auth/refresh` | 1,398 | 5.72s | 21.00s |
| `/api/student/exams/{exam}/start` | 740 | 18.10s | 125.73s |
| `/api/student/auth/refresh` | 681 | 24.44s | 120.00s |
| `/api/student/exams/submit` | 616 | 56.74s | 120.00s |
| `/api/exams/submit-answer` | 565 | 2.67s | 5.00s |
| `/api/teacher/grading/grade-essay` | 505 | 9.53s | 16.52s |
| `/api/teacher/stats/dashboard` | 269 | 8.50s | 73.66s |
| `/api/admin/monitoring/active-exams` | 75 | 5.60s | 64.38s |
| `/api/admin/monitoring/system/ops-summary` | 65 | 5.89s | 64.38s |

Catatan penting:

- WebSocket request log memiliki durasi ribuan detik karena koneksi WebSocket memang long-lived; ini tidak langsung berarti latency HTTP. Karena itu tabel slow di atas mengecualikan WebSocket.
- `/api/exams/submit-answer` relatif lebih terkendali dibanding batch/journal/final-submit, tetapi tetap ada 565 slow >2s.
- Final submit `/api/student/exams/submit` sangat berat: 616 slow, avg 56.74s, max 120s, plus 205 5xx dan 184 499. Ini P0.

## DB / PgBouncer / API Error Findings

API log aggregate hari ini:

| Signal | Count |
|---|---:|
| Slow request warnings | 123,243 |
| API warnings | 140,783 |
| API errors | 287 |
| Tracebacks | 711 |
| `ConnectionDoesNotExistError` / connection closed mid-operation | 297 |
| Timeout mentions | 653 |
| 503 mentions | 763 |

DB log aggregate hari ini:

| Signal | Count |
|---|---:|
| idle-in-transaction timeout | 219 |
| FATAL entries | 224 |
| ERROR entries | 26 |
| WARNING entries | 24 |
| deadlock | 0 |

Representative DB log patterns:

- `terminating connection due to idle-in-transaction timeout`
- `prepared statement "__asyncpg_..." does not exist`
- `you don't own a lock of type ExclusiveLock`

Interpretasi:

1. Ada transaction/connection yang menggantung cukup lama hingga DB memutus idle-in-transaction.
2. `ConnectionDoesNotExistError` di API kemungkinan merupakan efek lanjutan dari DB/pgbouncer memutus koneksi saat operation masih berjalan.
3. `prepared statement does not exist` mengarah ke interaksi asyncpg prepared statement cache dengan PgBouncer/connection reuse; perlu dicek setting engine/driver.
4. `you don't own a lock of type ExclusiveLock` perlu ditelusuri ke advisory unlock/release path atau operasi lock yang tidak simetris.
5. Deadlock tidak terlihat pada sample aggregate.

## Security / DDoS Assessment

Tidak ada indikasi kuat DDoS tunggal:

- Request volume tinggi tapi sesuai hari ujian dan tersebar pada endpoint exam/autosave/status.
- Top source terlihat banyak dari jaringan seluler/ISP berbeda; IP disanitasi.
- Rate limit 429 hanya 25, bukan pola utama.
- `security_events` hari ini: 0 aggregate.

Namun ada noise internet umum:

- 404/400 probing seperti `/robots.txt`, `/___proxy_subdomain_whm/login/`, `/GponForm/diag_Form`, `/shell`.
- Noise ini kecil dibanding traffic ujian dan bukan penyebab utama.

## Data Safety / Completion Assessment

Aggregate completion terlihat baik:

- Semua session hari ini pada query status berstatus `submitted`.
- Score present sama dengan session count per exam.
- `SESSION_START` = `SCORE_BREAKDOWN` = 863.
- Tidak ada `in_progress` saat dicek malam hari.
- Tidak ada security event aggregate.

Risiko yang masih perlu diaudit manual:

- 109 `EXAM_AUTO_SUBMITTED_TIMEOUT` perlu dicek apakah expected karena durasi ujian habis atau efek performance/connection delay.
- Final-submit path punya 205 5xx dan 184 499; meski aggregate score tampak lengkap, endpoint ini tetap wajib diprioritaskan agar tidak bergantung pada auto-submit/ retry behavior.

## Patch Priority Recommendation

### P0 — Final submit hardening

Evidence:

- `/api/student/exams/submit`: 1,420 requests, 616 slow >2s, avg 56.74s, max 120s, 205 5xx, 184 499.

Candidate work:

1. Profiling final submit query/transaction duration.
2. Pastikan final submit tidak menunggu publish/cache invalidation non-kritis sebelum response.
3. Review lock scope dan commit boundary.
4. Pastikan retry/idempotency path cepat untuk `submitted/completed`.
5. Tambah test guard untuk no extra heavy query pada already-submitted session.

### P0 — Reduce session status polling pressure

Evidence:

- `/api/exams/session/{id}/status`: 244,880 requests, 63,692 499, 68,368 slow >2s, 1,246 5xx.

Candidate work:

1. Increase polling interval/backoff di client.
2. Cache status response short TTL saat exam running.
3. Stop polling once session is terminal.
4. Prefer WebSocket event if connected, polling fallback only.
5. Aggregate/normalize endpoint path in monitoring to avoid per-session blow-up.

### P0 — Simplify answer sync/autosave concurrency

Evidence:

- `/api/exams/answer-journal/sync`: 61,665 requests, 1,199 5xx, 18,990 499, 25,767 slow.
- `/api/exams/auto-save-batch`: 34,950 requests, 1,735 5xx, 10,844 slow avg 33.18s.
- `/api/student/exams/auto-save-batch`: 31,438 requests, 1,782 5xx, 22,114 499, 25,795 slow.
- `/api/exams/submit-answer`: 84,196 requests but comparatively fewer slow requests (565 slow >2s).

Candidate work:

1. Confirm APK/web are not sending duplicate batch + journal + single answer for same event.
2. Enforce client-side debounce/min interval and in-flight dedupe.
3. Prefer one canonical sync route per client mode.
4. Keep Phase 4 patch that skips non-critical progress DB fallback during peak.
5. Measure direct-mode staging after reducing duplicate writes.

### P1 — DB/PgBouncer/asyncpg connection stability

Evidence:

- 219 idle-in-transaction timeouts.
- 297 connection closed mid-operation mentions.
- prepared statement missing errors.

Candidate work:

1. Inspect SQLAlchemy asyncpg connection arguments with PgBouncer mode.
2. Consider disabling asyncpg prepared statement cache if PgBouncer transaction pooling is used.
3. Audit long transaction scopes in answer sync, final submit, dashboard, and grading.
4. Add statement timeout/logging for slow query identification in staging first.

### P1 — Admin/teacher dashboard and grading pressure

Evidence:

- `/api/teacher/grading/grade-essay`: 505 slow, 202 499.
- `/api/teacher/stats/dashboard`: 269 slow, max 73.66s.
- `/api/admin/monitoring/*`: slow max 64.38s.

Candidate work:

1. Keep admin dashboard summary-only during active exam.
2. Disable or throttle detail monitoring under `EXAM_PEAK_MODE=true`.
3. Move heavy grading/dashboard queries outside exam peak or add pagination/cache.

### P2 — Static asset perceived slowness

Evidence:

- Static JS had slow/5xx entries during peak.

Interpretation:

- Static files are likely victims of upstream/server saturation or client network delay, not root cause.
- Still worth enabling stronger browser cache/versioning and checking nginx static serving isolation.

## Recommended Next Execution Plan

1. **Create P0 issue/branch: final submit hot path profiling and idempotent fast path.**
2. **Create P0 issue/branch: session status polling backoff/cache.**
3. **Create P0 issue/branch: answer sync client de-dup/debounce and canonical route selection.**
4. **Create P1 issue/branch: PgBouncer/asyncpg prepared statement and idle transaction audit.**
5. **Create P1 issue/branch: admin/teacher monitoring/grade/dashboard throttle during peak.**
6. Validate every patch in local/staging synthetic direct mode before production review.
7. Keep Phase 5 hybrid rollout blocked until direct path is stable.

## Operational Recommendation for Next Exam Day

- Use wave control: 150–200 peserta per login/start/final-submit wave.
- Keep `ADMIN_MONITORING_DETAIL_LEVEL=summary`.
- Avoid `results/all`, heavy grading, templates, and detail monitoring during active exam.
- Keep `HEAVY_EXPORT_ENABLED=false` during peak.
- Keep queue/hybrid off until direct-mode gates pass.
- Monitor specifically:
  - `/api/student/exams/submit` 5xx/499
  - `/api/exams/session/{id}/status` request rate
  - answer sync 5xx/499
  - DB idle-in-transaction timeout
  - PgBouncer pool wait/saturation

## Final Decision

- Production was not modified.
- No evidence of total crash at time of check.
- No strong evidence of DDoS as primary cause.
- There was significant exam-day performance degradation, especially polling/status, autosave/sync, and final submit.
- Data completion aggregate appears safe, but final-submit reliability must be patched before claiming exam-day stability.
- Phase 5 hybrid rollout remains **blocked**.
