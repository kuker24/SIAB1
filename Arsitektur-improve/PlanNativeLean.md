# Rencana implementasi — SIAB1 Native-Lean v2 (#3+)

Dokumen kerja. **Belum coding.** Keputusan arsitektur: `NewArstitketur.md`.

Urutan aman: **Kotlin native dulu → Go kemudian**. Hasil akhir = Go modular monolith + Kotlin kiosk + HTML renderer.

Fungsi sama. UI sama. Bukan microservice. Bukan HTMX. Bukan Compose soal. Bukan Flutter Web.

---

## 0. Kontrak yang tidak boleh pecah

- Ujian, admin, autosave, reconnect, audit, SXB/SEB, rate limit, lockout, CAPTCHA, JWT ujian **120 menit**.
- Tampilan admin: Bootstrap 5.3 + Font Awesome. Ujian: Inter + `exam.css` / `student.css`.
- Satu renderer soal: HTML di browser **dan** WebView. Kotlin tidak merender soal.
- Nginx: delapan lane siswa (`api`–`api8`) + dua lane admin. Postgres + Redis + PgBouncer tetap.
- Urutan kebijakan HTTP (Starlette reverse-add) harus setara di Go: CORS → security headers → rate limit → SXB → logging → performance. HTTPS redirect tetap mati (Cloudflare).
- `redirect_slashes=False` (jangan 307 hilangkan body).
- Jangan `docker compose down -v` di produksi. Jangan rebuild image saat ujian live.

Parity cutover: autosave, reconnect, SXB/SEB, JWT 120, kiosk, audit, tampilan familiar.

---

## 1. Keadaan sekarang (bukti repo)

| Bagian | Fakta |
| --- | --- |
| HTTP | FastAPI, `app/main.py`, ~40 router di `app/api/` |
| Hot path ujian | `app/api/exams.py` (`start_exam_session` ~2044–2565), `exam_answer_sync.py`, `final_submit.py`, `app/services/answer_sync_service.py` |
| SXB | `app/middleware/sxb_enforcer.py` |
| Worker | Celery: jawaban 5s, publikasi 60s, sesi kedaluwarsa 30s, analytics 5 mnt, partisi jam 02:15, DR Minggu |
| Renderer | `templates/student/exam.html` + `static/js/exam-system.js` (~2972 baris), include baris 1118 |
| APK | Flutter: splash → native login → `InAppWebView`. `exam_page.dart` 3680 baris, 12 JS handler |
| Kiosk | `MainActivity.kt` MethodChannel `startLockTask` / `FLAG_SECURE` / signature |
| Header SXB klien | `X-SafeExamBrowser-ConfigKeyHash`, UA SEB, `X-Build-Token`, `X-App-Signature`, `X-App-Timestamp`, `X-App-Version` |
| Deploy | `docker-compose.production.yml`: api×8 + api_admin×2, db, pgbouncer, redis, nginx, celery_worker, celery_beat |
| APK builder | `app/api/apk.py` + `tools/apk_builder_*` (Flutter) |
| Tes | `pytest -q`; gate `scripts/verify_release_gate.sh` |

Jinja di `templates/` minim (`extends`/`block`/`if`). Port ke Go `html/template` realistis tanpa ganti CSS.

---

## 2. Target pohon (side-by-side, jangan hapus Python/Flutter dulu)

```text
SIAB1/
├── android-kiosk/          # BARU — Gradle Kotlin, bukan Flutter
├── go/                     # BARU — modular monolith
│   ├── cmd/server/
│   ├── cmd/worker/
│   └── internal/
│       ├── exam/
│       ├── auth/
│       ├── student/
│       ├── admin/
│       ├── security/
│       ├── audit/
│       └── persistence/
├── templates/              # TETAP — HTML UI
├── static/                 # TETAP — CSS + JS (exam/ pecah nanti)
├── app/                    # Python sampai cutover Fase B
├── flutter_client_code/    # sampai APK Kotlin lulus parity
└── docker-compose.production.yml
```

Dua proses native akhir: `siab1-server`, `siab1-worker`.

---

## 3. Fase

Jangan campur Kotlin+Go+JS dalam satu PR. Setiap fase punya pintu keluar: Python/Flutter masih bisa jalan.

### Fase 0 — Inventaris kontrak (tanpa ganti bahasa)

Tujuan: daftar yang harus sama setelah konversi.

1. Katalog rute HTTP ujian/auth/admin (dari `app/main.py` include_router).
2. Katalog 12 JS handler di `exam_page.dart` (nama + arah data).
3. Katalog header SXB/APK di `api_service.dart` + cek server di `sxb_enforcer.py`.
4. Katalog beat Celery (`app/tasks/scheduler.py`).
5. Screenshot/referensi UI: login native, dashboard siswa, `exam.html` (bukan restyle).
6. Tulis `Arsitektur-improve/parity-checklist.md` saat Fase 0 dijalankan.

Selesai jika: checklist rute + handler + header + jadwal worker ada.

### Fase A — Kotlin native kiosk (Python tetap)

Tujuan: hapus Flutter dari jalur siswa. Backend tidak diubah.

Modul APK:

```text
Splash (warna #0f172a, aksen #3b82f6, Inter)
  → Native login (look sama dengan Flutter Material gelap)
  → WebView student dashboard / exam.html
```

Kotlin memegang: lock task, `FLAG_SECURE`, lifecycle, jaringan, reconnect trigger, blokir unduh/app luar, clipboard, screenshot, kebijakan WebView, JS bridge minimal.

Port dari:

| Sumber | Tujuan |
| --- | --- |
| `MainActivity.kt` | Activity kiosk, bukan `FlutterActivity` |
| `exam_page.dart` | WebView + 12 handler |
| `exam_resilience_service.dart` | reconnect / queue pelanggaran |
| `security_service.dart` | jailbreak, screenshot callback |
| `signature_verifier.dart` | `X-App-Signature` |
| `api_service.dart` | header SXB, token, runtime policy |
| `native_login_page.dart` | login XML/View, **bukan** Compose soal |
| `splash_page.dart` | splash |

JS bridge: `openImagePreview`, `securityHandler`, `setSessionId`, plus 9 handler lain — port nama **identik** agar `exam-system.js` tidak pecah.

`android-kiosk/` package baru (bukan `com.example.flutter_client_code`). Token build / signature tetap kompatibel dengan `ENFORCE_SXB`.

APK builder: `tools/apk_builder_*` arahkan ke `./gradlew assembleRelease` di `android-kiosk/`. Jangan panggil Flutter.

Selesai jika:

- APK buka URL siswa yang sama, soal HTML sama.
- Lock task + `FLAG_SECURE` + header SXB lulus tes perangkat.
- Flutter belum dihapus sampai APK ini dipakai.

Verifikasi: install debug APK; login; mulai ujian; autosave; putus jaringan; kiosk; bandingkan `exam.html` dengan Chrome/SEB.

### Fase A2 — Pecah JS ujian (boleh paralel dengan A, Python masih serve)

Tujuan: `exam-system.js` → module, **tanpa** ganti DOM/CSS.

```text
static/js/exam/
├── core.js
├── navigation.js
├── timer.js
├── autosave.js
├── reconnect.js
├── security.js
└── bridge.js
```

`templates/student/exam.html` ganti satu tag script menjadi daftar module (urutan dependency). `base.html` ikut jika masih memuat file lama.

Selesai jika: perilaku autosave/timer/navigasi identik; SEB PC tidak rusak; tidak ada HTMX.

Verifikasi: tes ujian browser + SEB + WebView; smoke HTTP path ujian.

### Fase B — Go modular monolith (APK sudah Kotlin)

Tujuan: ganti FastAPI + Celery. Template/static **file yang sama**.

Urutan dalam Fase B (jangan semua rute sekaligus):

1. **Skeleton** — `go/cmd/server` chi, health `/health`, static `/static`, `html/template` dari `templates/`.
2. **Security middleware** — padanan SXB, rate limit, headers, logging. JWT 120 menit.
3. **Auth + student pages** — login, dashboard, `exam.html` (output HTML familiar).
4. **Exam hot path** — start, autosave, sync, final submit. Port `AnswerSyncService` + `final_submit`.
5. **Admin routes** — CRUD, monitoring, websocket (`app/api/websocket.py` → gorilla/nhooyr).
6. **Worker** — `go/cmd/worker` Redis queue: jawaban 5s, close session 30s, publikasi 60s, views 5 mnt, partisi, DR.
7. **Shadow** — proses Go di Compose profile terpisah; Nginx masih ke Python sampai parity.

DB: driver Postgres (pgx) lewat PgBouncer. Redis: session/cache/antrian. Skema SQL **tidak** didesain ulang.

Jinja: port `extends`/`block`/`if` ke `html/template`. Jangan pongo2 kecuali tes HTML diff gagal.

Selesai jika: tes kontrak HTTP Go untuk start/autosave/submit; `/health`; SXB menolak klien ilegal.

Verifikasi: `go test ./...`; tes kontrak hot path; `SKIP_HTTP=1 bash scripts/verify_release_gate.sh` selama Python masih ada; smoke `/health` pada proses Go.

### Fase C — Compose, hapus runtime lama

Hanya setelah Fase A+B lulus.

- Image `siab1-server` / `siab1-worker` ganti `uvicorn` + `celery_worker` + `celery_beat`.
- Replica `api`–`api8` + `api_admin` tetap, binary Go.
- Hapus `app/` Python produksi, `flutter_client_code/`, Celery dari Compose.
- `scripts/check_security.py` / gate: sesuaikan ke binary Go + APK Gradle (jangan hilangkan cek SXB).
- Prometheus scrape target tetap; metrik Go (promhttp) padanan path yang dipakai Grafana.

Selesai jika: `docker compose -f docker-compose.production.yml config` valid; `ps` menampilkan server+worker, bukan celery.

### Fase D — Cutover VPS (eksplisit, bukan otomatis)

Jangan dijalankan tanpa permintaan operasional terpisah.

- Bukan saat ujian live. Bukan `down -v`.
- Backup Postgres dulu. Dual-run singkat: Nginx satu lane ke Go, sisanya Python, lalu pindah.
- `bash scripts/verify_stable_release_vps.sh` setelah sehat.
- APK Kotlin didistribusi lewat builder yang sudah diganti.

---

## 4. Peta file kritis

**Fase A**

- Baru: `android-kiosk/` (Gradle, Manifest lock-task, WebView).
- Baca: `flutter_client_code/lib/pages/exam_page.dart`, `native_login_page.dart`, `services/*.dart`, kedua `MainActivity.kt`.
- Ubah nanti: `tools/apk_builder_*`, `app/api/apk.py` (path artifact Gradle).

**Fase A2**

- Pecah: `static/js/exam-system.js`.
- Sentuh: `templates/student/exam.html`, `templates/base.html`.
- Jangan sentuh: `static/css/exam.css`.

**Fase B**

- Baru: `go/cmd/server`, `go/cmd/worker`, `go/internal/*`.
- Port perilaku: `app/api/exams.py`, `exam_answer_sync.py`, `final_submit.py`, `auth.py`, `middleware/sxb_enforcer.py`, `services/answer_sync_service.py`, `tasks/scheduler.py`, `tasks/answer_processor.py`, `main.py` (urutan middleware + template).
- Tetap: `templates/`, `static/`, `docker/nginx.production.conf` (upstream ganti host/port saja di Fase C).

**Jangan**

- Microservice.
- HTMX di jalur autosave.
- Compose UI soal.
- Ganti Postgres/Redis.
- Restyle CSS.

---

## 5. Risiko

| Risiko | Mitigasi |
| --- | --- |
| `exam_page.dart` 3680 baris, 12 handler | Katalog Fase 0; port nama handler identik |
| Jinja vs `html/template` | HTML diff halaman kunci; CSS tidak diubah |
| SXB putus setelah ganti APK | Header + signature + build token kompatibel; tes enforcer |
| Celery beat terlewat | Jadwal worker disalin 1:1 |
| APK builder masih Flutter | Fase A wajib ganti Gradle |
| Ujian live | Fase D manual; dual-run; tanpa `down -v` |
| WebSocket monitoring | Port di B5 sebelum cutover admin |
| Dua `MainActivity.kt` | Satu kiosk Kotlin; buang salinan `android_src` setelah parity |

---

## 6. Verifikasi per fase

| Fase | Perintah / bukti |
| --- | --- |
| 0 | Checklist rute/handler/header tertulis |
| A | APK debug: kiosk + WebView + autosave + SXB header |
| A2 | Ujian browser + SEB + WebView, CSS sama |
| B | `go test ./...`; kontrak start/autosave/submit; SXB tolak |
| C | Compose tanpa Celery/uvicorn; `/health` |
| D | `verify_stable_release_vps.sh` (hanya jika diminta) |

Python selama masih hidup: `python -m compileall app`, `pytest -q` (atau node ID target), `python scripts/check_security.py`.

---

## 7. Default yang sudah dikunci

- Fondasi **#3+**, bukan HTMX, bukan microservice.
- Login APK tetap **native** (look Flutter gelap), soal tetap **HTML**.
- Go di `go/`, APK di `android-kiosk/`, Python/Flutter hidup sampai fase masing-masing lulus.
- Dual-run Go di belakang Nginx sampai parity, baru cutover.
- Coding **belum** dimulai. Langkah berikutnya hanya jika Anda minta fase tertentu (0 / A / A2 / B).

---

## 8. Status

Rencana dijalankan di repo: Fase 0–C (shadow). Fase D VPS tidak dijalankan. Python/Flutter belum dihapus.
