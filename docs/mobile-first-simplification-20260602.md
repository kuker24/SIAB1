# Mobile-First Ujian Online Simplification

Tanggal: 2026-06-02

Dokumen Phase 0 ini mengaudit fitur dan endpoint Ujian Online untuk menyederhanakan arsitektur menuju runtime utama:

```text
Mobile APK official = primary exam runtime
SEB PC/Desktop = optional legacy
```

Phase 0 hanya dokumentasi. Tidak ada perubahan logic, route registration, database schema, atau UI.

## 1. Prinsip prioritas

Prioritas sistem saat ujian aktif:

```text
1. Jawaban siswa aman.
2. Final submit selalu prioritas.
3. APK Android/HP tetap jalan.
4. Deteksi kecurangan tetap tampil di dashboard admin.
5. Fitur non-kritis boleh optional, async, cached, throttled, atau disabled-by-default.
```

Batas penting:

- Jangan rewrite total.
- Jangan hapus fitur inti.
- Jangan microservices besar.
- Jangan commit APK/AAB/keystore/env/data siswa.
- Jangan mengubah APK signature/header validation secara tidak sengaja.
- Jangan melemahkan SXB/mobile runtime.

## 2. Core mobile/APK yang wajib dipertahankan

Source dan runtime utama:

```text
flutter_client_code/
app/api/apk.py
app/middleware/sxb_enforcer.py
app/middleware/seb_validation.py
app/api/sxb.py
app/core/sxb_security.py
app/core/apk_profiles.py
app/utils/apk_validation.py
```

Fitur wajib dipertahankan:

```text
- APK Android / HP exam runtime
- APK build token
- APK token validation endpoint
- APK signature validation/header
- kiosk/secure mode mobile
- screenshot/task switch/root/tamper detection mobile
- login siswa
- join token
- start exam
- timer
- answer autosave/journal
- offline-first recovery
- final submit
- grading/result
- admin dashboard
- admin cheating detection/monitoring
- emergency exit/admin command
```

Endpoint APK/mobile yang harus tetap aman:

```text
GET  /api/v1/apk/config
GET  /api/v1/apk/download
GET  /api/v1/apk/info
GET  /api/v1/apk/version
POST /api/v1/apk/validate-token
POST /api/validate-apk-token
GET  /api/sxb/config
POST /api/sxb/verify-signature
```

Catatan:

- APK download/info boleh tetap aktif agar distribusi APK resmi tidak terganggu.
- Yang boleh dimatikan default adalah build APK dari production server, bukan download/info APK.

## 3. SEB PC/Desktop yang bisa menjadi legacy optional

File/fitur terkait SEB desktop/generic:

```text
app/api/seb_autoconfig.py
app/api/exam_seb.py
app/api/seb_builder.py
app/core/seb.py
app/models/seb_build.py
app/models/seb_config_template.py
templates/seb/
```

Endpoint yang bisa disabled-by-default jika SEB PC tidak dipakai sebagai jalur utama:

```text
GET  /api/seb/download-config
GET  /api/seb/config-info
GET  /api/seb/debug/url-rules
GET  /api/seb/exam/{exam_id}/download-config
GET  /api/exams/default-seb-config.seb
GET  /api/exams/{exam_id}/seb-config.seb
POST /api/v1/seb-builder/configure
POST /api/v1/seb-builder/build
GET  /api/v1/seb-builder/builds
GET  /api/v1/seb-builder/download/{build_id}
```

QR/generic Exambro/SEB flow yang bisa disabled-by-default jika tidak dipakai:

```text
GET /api/seb/qr-code
GET /api/seb/exam/{exam_id}/qr-code
GET /api/exams/seb-qrcode
GET /api/exams/{exam_id}/seb-qr
GET /api/exams/{exam_id}/seb-launch-mobile
```

Risiko menjadikan SEB desktop legacy:

- Peserta yang masih memakai PC/desktop SEB tidak bisa masuk jika flag dimatikan.
- Dokumentasi lama/admin UI perlu diperbarui agar tidak membingungkan.
- QR flow generik Exambro lama tidak tersedia jika `SEB_QR_ENABLED=false`.

Mitigasi:

- Jangan hapus permanen.
- Gunakan feature flag.
- Default fokus APK official.
- Bisa re-enable jika sekolah masih butuh SEB desktop.

## 4. Admin cheating detection yang wajib tetap ada

Fitur wajib tetap ada:

```text
- Deteksi screenshot/task switch/root/tamper/visibility/fullscreen/accessibility.
- Violation count per session.
- Risk/severity per peserta.
- Status suspicious/normal/high-risk di dashboard admin.
- Emergency exit/admin command.
- Monitoring summary saat ujian berlangsung.
```

File/area terkait:

```text
app/api/exams.py                     # POST /api/exams/log-violation
app/api/monitoring.py                # monitoring dashboard/export/summary
app/core/violation_metadata.py
app/core/violation_scoring.py
static/js/admin/monitoring.js
static/js/admin/monitoring/modules/
templates/admin/monitoring.html
```

Target arah baru:

```text
Violation request hot path -> validate ringan -> Redis queue/cache -> response cepat
Worker/batch -> PostgreSQL
Dashboard -> aggregate-first, detail lazy-load/paginated
```

Yang tidak boleh terjadi:

- Violation log memblokir final submit.
- Violation log membuat autosave gagal.
- Dashboard menarik semua raw event setiap beberapa detik.

## 5. Fitur non-kritis yang bisa async/optional

Fitur yang boleh dijadikan optional/legacy/throttled:

```text
1. SEB PC/Desktop .seb config generator.
2. SEB desktop QR/config-info/debug-url-rules.
3. Generic Exambro/SEB QR flow jika tidak dipakai.
4. APK build endpoint di production saat ujian aktif.
5. Telegram alerting jika bukan mandatory.
6. PDF/report/export berat saat exam_peak.
7. Analytics detail realtime.
8. Monitoring detail terlalu granular.
9. Prometheus/Grafana scrape agresif.
10. Debug endpoints yang tidak diperlukan saat production.
```

Risiko dan mitigasi:

| Fitur | Risiko jika dipangkas | Mitigasi |
|---|---|---|
| SEB desktop config | PC/desktop SEB tidak bisa dipakai | Legacy flag dapat diaktifkan lagi |
| SEB QR generic | Exambro/QR lama tidak jalan | APK official tetap jalur utama |
| APK build endpoint | Admin tidak bisa build dari VPS | Build APK lokal/CI, download/info tetap aktif |
| Telegram | Alert eksternal hilang | Dashboard/internal alert tetap ada |
| PDF/report/export | Laporan tertunda | Disable hanya saat exam_peak |
| Analytics detail realtime | Detail observability turun | Summary/cache tetap tersedia |
| Raw violation realtime | Detail investigasi tertunda | Lazy-load/paginated detail |
| Prometheus scrape agresif | Metrik granular turun | Scrape interval disesuaikan saat peak |

## 6. Endpoint hot-path siswa

Endpoint yang paling penting untuk jalannya ujian:

### P0 - final submit

```text
POST /api/exams/submit
POST /api/exams/sessions/{session_id}/force-submit
```

Catatan:

- `/api/exams/submit` adalah submit final siswa.
- Force submit adalah admin/emergency path dan harus tetap idempotent/safe.

### P1 - answer sync/autosave/journal/session/timer

```text
POST /api/exams/submit-answer
POST /api/exams/auto-save
POST /api/exams/auto-save-batch
POST /api/exams/answer-journal/sync
GET  /api/exams/session/{session_id}/status
GET  /api/exams/session/{session_id}/remaining-time
```

Catatan:

- Hot endpoint ini pernah menjadi sumber pressure terbesar saat insiden traffic.
- Perlu backoff/jitter/adaptive sync dan service internal tunggal di fase lanjutan.

### P2 - recovery/admin command

```text
GET  /api/exams/session/{session_id}/offline-package
GET  /api/exams/session/{session_id}/resume
POST /api/exams/{exam_id}/pause-all
POST /api/exams/{exam_id}/resume-all
GET  /api/exams/{exam_id}/pause-status
```

Catatan:

- Penting untuk recovery dan kontrol admin.
- Tidak boleh membebani final submit.

### P3 - cheating aggregate/monitoring summary

```text
POST /api/exams/log-violation
GET  /api/monitoring/...
GET  /api/stats/...
```

Catatan:

- Deteksi kecurangan wajib tetap ada.
- Target baru adalah aggregate-first, queue/cache, dan throttled polling.

### P4 - non-critical/detail/export/legacy

```text
GET /api/monitoring/violations/export
GET /api/exams/{exam_id}/participation-summary/export
GET /api/exams/{exam_id}/analytics/pdf
GET /api/exams/{exam_id}/results/pdf
GET /api/exams/{exam_id}/sessions/{session_id}/certificate
POST /api/users/export
POST /api/v1/telegram/send
GET /api/seb/download-config
GET /api/seb/config-info
GET /api/seb/debug/url-rules
GET /api/seb/qr-code
GET /api/seb/exam/{exam_id}/download-config
GET /api/seb/exam/{exam_id}/qr-code
GET /api/exams/default-seb-config.seb
GET /api/exams/seb-qrcode
GET /api/exams/{exam_id}/seb-config.seb
GET /api/exams/{exam_id}/seb-qr
GET /api/exams/{exam_id}/seb-launch-mobile
POST /api/v1/apk-builder/build
POST /api/v1/seb-builder/build
```

## 7. Endpoint non-kritis menurut mode ujian

Saat `EXAM_PEAK_MODE=true`, kandidat endpoint yang harus disabled/throttled:

```text
- PDF/report/export berat.
- Telegram broadcast/alerting.
- SEB desktop builder/config debug.
- APK build dari server production.
- Raw violation detail export.
- Analytics detail realtime.
```

Tetap aktif saat peak:

```text
- login siswa.
- join token.
- start exam.
- answer autosave/journal.
- session/timer.
- final submit.
- APK token/signature validation.
- dashboard summary cheating aggregate.
- emergency/admin command.
```

## 8. Feature flag yang diperlukan

Feature flags Phase 1:

```text
MOBILE_APK_PRIMARY=true
SEB_DESKTOP_LEGACY_ENABLED=false
SEB_QR_ENABLED=false
SEB_DEBUG_ENDPOINTS_ENABLED=false
APK_BUILD_ENDPOINT_ENABLED=false
TELEGRAM_ALERTING_ENABLED=false
HEAVY_EXPORT_ENABLED=true
EXAM_PEAK_MODE=false
ADMIN_MONITORING_DETAIL_LEVEL=summary
VIOLATION_ASYNC_ENABLED=true
```

Makna ringkas:

| Flag | Default | Makna |
|---|---:|---|
| `MOBILE_APK_PRIMARY` | `true` | Menandai APK official sebagai jalur utama |
| `SEB_DESKTOP_LEGACY_ENABLED` | `false` | Re-enable SEB PC/Desktop legacy jika perlu |
| `SEB_QR_ENABLED` | `false` | Re-enable QR generic SEB/Exambro jika perlu |
| `SEB_DEBUG_ENDPOINTS_ENABLED` | `false` | Re-enable endpoint debug SEB |
| `APK_BUILD_ENDPOINT_ENABLED` | `false` | Izinkan build APK dari server production |
| `TELEGRAM_ALERTING_ENABLED` | `false` | Izinkan alert Telegram operasional |
| `HEAVY_EXPORT_ENABLED` | `true` | Izinkan export/report berat di luar peak |
| `EXAM_PEAK_MODE` | `false` | Mode ujian puncak, non-kritis dibatasi |
| `ADMIN_MONITORING_DETAIL_LEVEL` | `summary` | Detail monitoring default |
| `VIOLATION_ASYNC_ENABLED` | `true` | Persiapan Phase 2 async violation |

## 9. Rencana PR bertahap

### PR/Commit 1 - Phase 0 documentation

Scope:

```text
- Tambah docs/mobile-first-simplification-20260602.md
- Tidak ada logic change
- Tidak ada schema change
```

Rollback:

```text
- Hapus dokumen saja.
```

### PR/Commit 2 - Phase 1 feature flags dan guard low-risk

Scope:

```text
- Tambah settings flags.
- Tambah env example.
- Guard SEB desktop legacy endpoints and hide SEB PC generate/download UI when `SEB_DESKTOP_LEGACY_ENABLED=false`.
- Guard SEB QR/debug endpoints.
- Guard APK build endpoint saja.
- Guard Telegram alerting.
- Guard heavy export/report saat EXAM_PEAK_MODE=true.
```

Tidak termasuk:

```text
- Redis violation queue.
- AnswerSyncService.
- FinalSubmitService.
- APK Flutter interval/backoff.
- DB schema change.
```

Rollback:

```text
- Set SEB_DESKTOP_LEGACY_ENABLED=true jika butuh PC SEB; admin SEB Builder form/link remains hidden while false.
- Set SEB_QR_ENABLED=true jika butuh QR legacy.
- Set APK_BUILD_ENDPOINT_ENABLED=true jika admin perlu build dari server.
- Set TELEGRAM_ALERTING_ENABLED=true jika Telegram mandatory.
- Set EXAM_PEAK_MODE=false untuk membuka export/report.
```

### PR lanjutan - Phase 2+

Urutan aman:

```text
1. Violation async/cache aggregate.
2. Runtime policy endpoint untuk APK.
3. APK/web backoff+jitter.
4. AnswerSyncService internal direct mode.
5. Redis runtime buffer bertahap/hybrid.
6. FinalSubmitService priority.
7. Dashboard cheating aggregate-first.
8. APK release/debug cleartext cleanup.
9. SEB desktop legacy UI cleanup.
10. Admin UI simplification.
11. Split app/api/exams.py setelah service stabil.
```

## 10. Risiko utama rencana keseluruhan

| Risiko | Dampak | Kontrol |
|---|---|---|
| Salah mematikan endpoint APK | APK tidak bisa login/start | Flag hanya menyentuh legacy SEB/APK build, bukan APK runtime |
| Violation async drop event | Detail kecurangan kurang lengkap | Aggregate tetap ada, detail best-effort, deadletter |
| Backoff terlalu lambat | Recovery jawaban terlambat | Final submit forced flush dan bounded retry |
| Queue Redis gagal | Autosave terganggu | Fallback direct/controlled 503 sesuai mode |
| SEB desktop masih dipakai sebagian | Peserta PC terganggu | Flag legacy bisa diaktifkan lagi |
| Export dimatikan saat peak | Admin menunggu laporan | Hanya saat peak; export kembali setelah ujian |

## 11. Definition of done jangka akhir

Target akhir:

```text
- APK HP tetap bisa login/start/ujian/submit.
- Cheating detection tetap tampil di dashboard admin.
- SEB PC tidak lagi membebani mental model/runtime utama.
- Violation log tidak membebani DB langsung.
- Autosave/journal lebih hemat.
- Final submit prioritas.
- Tidak ada output APK/signing key/secret masuk repo.
- Load test menunjukkan DB pressure turun.
```

## 12. Production rollout

Bagian ini menjadi panduan aman untuk production setelah fase mobile-first dan service-boundary answer sync diterapkan.

### 12.1 Safe production baseline

Gunakan baseline berikut untuk production saat ujian aktif, terutama sebelum runtime answer buffer dibuktikan lewat staging/load test:

```env
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
SEB_DESKTOP_LEGACY_ENABLED=false
SEB_QR_ENABLED=false
APK_BUILD_ENDPOINT_ENABLED=false
TELEGRAM_ALERTING_ENABLED=false
```

Makna operasional:

- Jawaban siswa tetap direct-write sebagai mode paling kompatibel.
- Runtime answer buffer/queue tetap off secara default.
- Violation logging tetap async agar tidak membebani jalur jawaban/final submit.
- Monitoring admin default summary/aggregate-first.
- SEB desktop, QR legacy, APK build server, dan Telegram alerting tetap disabled-by-default.

### 12.2 Staged rollout runtime answer buffer

Runtime answer buffer tidak boleh langsung 100% di production tanpa pembuktian final submit flush. `ANSWER_QUEUE_PERCENTAGE` hanya mengatur routing session baru ke jalur async/buffer, bersifat deterministik per session, dan session yang sama akan sticky ke jalur direct atau buffer selama nilai env tidak berubah. Menurunkan percentage ke `0` menghentikan session baru masuk buffer, tetapi flush/drain buffer lama tetap boleh berjalan selama `ANSWER_QUEUE_ENABLED=true` dan mode masih `queue`/`hybrid`. Gunakan canary bertahap 10% → 50% → 100% setelah test dan monitoring stabil.

#### Stage 0 — direct mode only

```env
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
```

Tujuan:

- Baseline production aman.
- Tidak ada session yang masuk runtime buffer karena percentage 0%.
- Semua single answer, autosave, journal, dan final submit tetap kompatibel dengan behavior existing.

#### Stage 1 — hybrid canary 10%

```env
ANSWER_WRITE_MODE=hybrid
ANSWER_QUEUE_ENABLED=true
ANSWER_QUEUE_PERCENTAGE=10
```

Syarat:

- Jalankan di staging lebih dulu.
- Hanya deterministic subset sekitar 10% session yang masuk runtime buffer.
- Verifikasi final submit selalu flush runtime buffer sebelum grading.
- Pantau error 503 submit dan ukuran pending Redis.

#### Stage 2 — hybrid 50%

```env
ANSWER_WRITE_MODE=hybrid
ANSWER_QUEUE_ENABLED=true
ANSWER_QUEUE_PERCENTAGE=50
```

Syarat:

- Stage 1 stabil.
- Deterministic subset sekitar 50% session masuk runtime buffer.
- Tidak ada penurunan answered_count/dashboard.
- Tidak ada kehilangan jawaban pada refresh/final submit.

#### Stage 3 — hybrid/queue 100%

```env
ANSWER_WRITE_MODE=hybrid
ANSWER_QUEUE_ENABLED=true
ANSWER_QUEUE_PERCENTAGE=100
```

Syarat keras:

- Semua eligible session masuk runtime buffer.
- Load test sudah melewati target concurrency production.
- Final submit flush terbukti aman.
- Redis, DB, worker drain, dan observability sudah stabil.

### 12.3 Rollback cepat

Jika ada gejala jawaban terlambat, pending Redis naik, atau submit sering 503:

Rollback total:

```env
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
```

Graceful drain rollback jika masih ada dirty buffer/pending Redis dan operator ingin menghentikan session baru masuk buffer sambil tetap mengizinkan flush:

```env
ANSWER_WRITE_MODE=hybrid
ANSWER_QUEUE_ENABLED=true
ANSWER_QUEUE_PERCENTAGE=0
```

Setelah pending/dirty buffer kosong, pindahkan ke rollback total (`direct`/`off`).

Tetap pertahankan jika stabil:

```env
VIOLATION_ASYNC_ENABLED=true
```

Saat traffic ujian puncak, tetap gunakan:

```env
ADMIN_MONITORING_DETAIL_LEVEL=summary
```

Jika export/report berat mengganggu peak traffic:

```env
EXAM_PEAK_MODE=true
```

Catatan rollback:

- Rollback env di atas tidak membutuhkan schema migration.
- Jangan restart saat ujian aktif kecuali benar-benar perlu dan disetujui operator.
- Jika restart harus dilakukan, prioritaskan window kosong dan backup konfigurasi terlebih dahulu.
