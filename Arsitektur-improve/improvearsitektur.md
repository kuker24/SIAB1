# Improve arsitektur SIAB1 — konversi bahasa, arsitektur tetap

Dokumen pemilihan. **Belum ada ubah kode.** UI tampilan tetap familiar. Arsitektur (lima lane, satu renderer soal HTML, WebView kiosk, SXB/SEB, JWT 120 menit) tidak didesain ulang — hanya dikonversi ke bahasa yang lebih ringan/powerful.

Repo: `SIAB1` (ujian online). Tanggal: 2026-08-21.

## Aturan yang tidak boleh pecah

- Lima lane: HTTP ujian/admin, browser UI, exam client (kiosk), data plane (PostgreSQL + Redis), ops (Bash/Docker/Nginx/Gradle).
- Satu renderer soal: HTML + CSS (`exam.css` / `student.css`) di browser **dan** di WebView APK. Bukan dua renderer (bukan Compose/Flutter widget soal).
- Tampilan tetap: admin Bootstrap 5.3 + Font Awesome; ujian Inter + token slate/blue. Jangan ganti look.
- Kontrak: SXB/SEB, rate limit, lockout, CAPTCHA, audit, `redirect_slashes=False`, urutan middleware, JWT ujian 120 menit.
- Data plane tetap PostgreSQL + Redis + PgBouncer. Bukan ganti database.
- Folder ≠ owner: SQL di `app/` tetap data plane; Gradle di Flutter tetap ops.

## Keadaan sekarang (bahasa)

| Lane | Bahasa / runtime | File inti |
|---|---|---|
| HTTP ujian/admin | Python 3.11, FastAPI 0.135.1, Celery 5.6.2 | `app/main.py`, `app/api/`, `app/core/` — `.py` 254 |
| Browser UI | HTML + Jinja2, vanilla JS, CSS | `templates/` 29 HTML, `static/js` 95 JS, `static/css` 10 |
| Exam client APK | Dart/Flutter 2.0.0+2 + Kotlin kiosk | `flutter_client_code/lib/pages/exam_page.dart` (3680 baris WebView), `MainActivity.kt` (329 baris) |
| Data | SQL PostgreSQL 15, Redis (protokol) | `app/migrations/`, `docker/init.sql` |
| Ops | Bash, Dockerfile, YAML, Nginx, Gradle | `docker-compose.production.yml`, `docker/nginx.production.conf` |

Fakta gesekan:

- Soal **bukan** di Dart. Flutter memuat `/student/dashboard.html` lalu `exam.html` + `exam-system.js` (2972 baris).
- Kiosk/screenshot/copy-paste/tab-switch terpecah di Kotlin + Dart + JS.
- Hapus Flutter **tidak** otomatis jadi kiosk Kotlin: Kotlin hari ini `FlutterActivity` + MethodChannel, bukan `WebView`. Perlu adapter WebView baru di Kotlin, port jurnal jawaban / reconnect dari Dart.
- Admin = Bootstrap; ujian siswa = CSS custom. Itu tetap.

## Kosakata (module / seam / adapter)

- **Module** ujian: `templates/student/exam.html` + `static/js/exam-system.js` + `static/css/exam.css`.
- **Adapter** APK: Flutter `InAppWebView` (dangkal, interface hampir selebar implementasi 3680 baris).
- **Seam** kiosk: Kotlin `startLockTask` / `FLAG_SECURE` — harus satu module, bukan tiga salinan.
- **Locality**: bug sesi ujian sekarang memantul HTML/JS/Dart/Kotlin.
- **Leverage**: ganti bahasa HTTP lane atau ganti adapter APK; jangan ganti renderer soal.

## Sepuluh rekomendasi

Kekuatan: `Strong` / `Worth exploring` / `Speculative`.

### 1. Kotlin WebView kiosk — buang Flutter/Dart

- **Bahasa:** Kotlin (APK). Python + HTML + JS **tetap**.
- **Files:** `flutter_client_code/` diganti modul Android native; `MainActivity.kt`; port dari `exam_page.dart`, `exam_resilience_service.dart`, `security_service.dart`; `templates/student/*` tidak diubah.
- **Problem:** adapter Dart dangkal; engine Flutter berat di HP siswa; kiosk bocor ke tiga bahasa.
- **Solution:** satu adapter Kotlin: `WebView` + JS interface + lock-task. HTML ujian sama.
- **Wins:** APK lebih kecil; locality kiosk di Kotlin; UI identik; Python tidak disentuh.
- **Kekuatan:** Strong.
- **Ketergantungan:** in-process (Android).

### 2. Go mengganti Python di HTTP lane — UI dan APK tetap

- **Bahasa:** Go (chi/echo/fiber + worker Asynq/River). Dart/Flutter + HTML/JS tetap.
- **Files:** `app/` → modul Go; `app/api/exams.py` dan middleware SXB port; static + templates disajikan apa adanya; Celery → worker Go.
- **Problem:** FastAPI + Celery + 254 file Python; hotspot `exams.py`; eight student lanes butuh runtime lebih ramping.
- **Solution:** HTTP lane Go, template/CSS/JS **file yang sama** (html/template atau embed `templates/` + `static/`).
- **Wins:** throughput; binary satu file; UI familiar; APK tidak diubah.
- **Kekuatan:** Strong.
- **Ketergantungan:** ports & adapters (HTTP + Postgres + Redis).

### 3. Go HTTP lane + Kotlin WebView — top rekomendasi

- **Bahasa:** Go + Kotlin + HTML/JS/CSS (tanpa Dart, tanpa Python runtime produksi).
- **Files:** gabungan #1 dan #2.
- **Problem:** dua runtime berat (CPython + Flutter engine) untuk produk yang soalnya sudah HTML.
- **Solution:** konversi dua adapter/runtime; renderer soal tidak diganti.
- **Wins:** APK ringan; backend powerful; tampilan sama; lima lane tetap.
- **Kekuatan:** Strong.
- **ADR:** Flutter-sebagai-WebView **dipertahankan sebagai pola** (WebView tetap); yang diganti hanya bahasa adapter (Dart→Kotlin) dan bahasa HTTP (Python→Go).

### 4. Rust (Axum) HTTP lane — APK Flutter tetap

- **Bahasa:** Rust. Flutter + HTML/JS tetap.
- **Files:** `app/` → crate Axum/Tower; sqlx/diesel ke PostgreSQL; Redis via fred/redis-rs.
- **Problem:** sama dengan #2, butuh memory/latency lebih ketat.
- **Solution:** binary Rust, static files identik.
- **Wins:** memory; safety; UI sama.
- **Tradeoff:** port lebih lama dari Go; talent lebih langka.
- **Kekuatan:** Worth exploring.

### 5. Rust Axum + Kotlin WebView

- **Bahasa:** Rust + Kotlin + HTML/JS/CSS.
- **Files:** #1 + #4.
- **Problem:** konversi penuh dua runtime.
- **Solution:** HTTP Rust, kiosk Kotlin, soal HTML.
- **Wins:** power maksimal di server + APK tanpa Flutter.
- **Kekuatan:** Worth exploring.
- **Risiko:** dua rewrite bersamaan; pecah jadi #4 lalu #1.

### 6. Kotlin di dua sisi — Ktor + WebView

- **Bahasa:** Kotlin (Ktor server + Android). HTML/JS tetap.
- **Files:** backend Ktor; APK WebView; coroutines; Exposed/jOOQ ke Postgres.
- **Problem:** hari ini Kotlin hanya snippet kiosk di bawah Flutter.
- **Solution:** satu bahasa untuk HTTP lane dan exam client; JS hanya di browser.
- **Wins:** satu skill Kotlin; kiosk dan server share model DTO jika diinginkan (jangan bocor ke HTML).
- **Kekuatan:** Worth exploring.
- **Tradeoff:** JVM di VPS lebih berat dari Go/Rust kecuali Graal.

### 7. Elixir/Phoenix HTTP lane + Kotlin WebView

- **Bahasa:** Elixir + Kotlin + HTML/JS.
- **Files:** Phoenix menyajikan `templates/` + `static/`; BEAM untuk banyak sesi; Celery diganti Oban/Broadway.
- **Problem:** delapan lane siswa + websocket monitoring = concurrency.
- **Solution:** BEAM di HTTP lane; APK Kotlin; UI HTML sama.
- **Kekuatan:** Speculative.
- **Tradeoff:** ekosistem ops beda dari Compose Python/Go di VPS ini.

### 8. Go + HTMX (CSS sama) + Kotlin WebView

- **Bahasa:** Go + HTMX + Kotlin. Vanilla `exam-system.js` disusutkan.
- **Files:** `exam.html` tetap class/CSS; potongan JS 2972 baris diganti request HTML parsial; `exam.css` tidak diganti.
- **Problem:** module ujian dangkal di JS (interface hampir = implementasi bundle).
- **Solution:** otoritas timer/soal/submit di server; HTMX sebagai adapter kecil; look identik.
- **Wins:** JS mengecil; locality di server; APK ringan.
- **Kekuatan:** Worth exploring.
- **Peringatan ADR:** “jangan tambah framework di path ujian” — HTMX boleh hanya jika CSS/DOM familiar, bukan SPA baru.
- **Risiko:** SEB + HTMX harus diuji; jangan pecah autosave.

### 9. TypeScript (Hono/Bun atau Node) HTTP lane + Kotlin WebView

- **Bahasa:** TypeScript + Kotlin + HTML/JS.
- **Files:** Hono/Fastify; serve static sama; worker BullMQ; APK Kotlin.
- **Problem:** ingin tipe di server tanpa Rust/Go.
- **Solution:** TS di HTTP lane; UI file sama.
- **Kekuatan:** Speculative.
- **Tradeoff:** Bun/Node di VPS ujian belum kontrak ops; bukan jelas lebih ringan dari Go.

### 10. Java 21 virtual threads + Graal native + Kotlin WebView

- **Bahasa:** Java 21 + Kotlin + HTML/JS.
- **Files:** Helidon/Quarkus/Spring native; virtual threads ganti async Python; APK Kotlin.
- **Problem:** satu keluarga JVM dengan Android.
- **Solution:** native image di VPS; WebView di HP; HTML sama.
- **Kekuatan:** Speculative.
- **Tradeoff:** image/build lebih berat dari Go; Graal butuh disiplin reflection.

## Yang ditolak (ubah tampilan atau dua renderer)

- Jetpack Compose merender soal (dua renderer).
- Flutter widget soal / Flutter Web (ganti look, SEB ragu).
- React / Vue / Svelte SPA yang mengganti `exam.css`.
- Ganti PostgreSQL atau Redis.
- Ganti Nginx lane atau kontrak SXB.

## Perbandingan bahasa (ringkas)

| Bahasa | Peran | Lebih ringan? | Lebih powerful? | Cocok UI-tetap? |
|---|---|---|---|---|
| Kotlin | APK kiosk WebView | Ya (tanpa Flutter engine) | Ya (kiosk native) | Ya |
| Go | HTTP lane + worker | Ya (binary, memori) | Ya (goroutine, 8 lane) | Ya (serve HTML sama) |
| Rust | HTTP lane | Ya (memori) | Ya (safety, latency) | Ya |
| Elixir | HTTP lane | Sedang | Ya (concurrency) | Ya |
| TypeScript | HTTP lane | Tidak jelas | Tipe | Ya |
| Java 21 + Graal | HTTP lane | Sedang (native) | Virtual threads | Ya |
| Python | HTTP lane sekarang | Baseline | Cukup, hotspot `exams.py` | Ya |
| Dart/Flutter | Adapter WebView sekarang | Tidak (engine) | Tidak untuk soal (tidak merender soal) | Look APK shell saja |
| HTML/CSS/JS | Renderer soal | Tetap | Tetap | Wajib |

## Urutan implementasi jika suatu saat coding (bukan sekarang)

1. Pilih nomor 1–10.
2. Port kontrak tes dulu (SXB, autosave, JWT 120, kiosk) — bukan fitur baru.
3. Static `templates/` + `static/css` + `static/js` di-copy, jangan restyle.
4. APK: WebView memuat URL siswa yang sama.
5. Cutover lane Nginx setelah parity tes.

## Rekomendasi teratas

**Nomor 3 — Go + Kotlin WebView + HTML/CSS/JS sama.**

Alasan satu kalimat: soalnya sudah HTML, Flutter hanya adapter, Python bisa diganti Go tanpa menyentuh tampilan.

Jika blast radius harus kecil: **nomor 1 dulu** (Kotlin saja), Go belakangan (**nomor 2**).

## Pilih

Nomor mana yang mau di-grill (1–10)? Setelah pilih, baru desain module/interface — masih **tanpa coding** sampai Anda minta.
