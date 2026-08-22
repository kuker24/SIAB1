# Arsitektur baru — 10 opsi konversi bahasa

Pemilihan stack. **Tidak ada ubah kode.** Arsitektur lama tetap: lima lane, satu renderer soal HTML, tampilan familiar, SXB/SEB, JWT 120 menit, PostgreSQL + Redis.

Baca lengkap: `improvearsitektur.md` di folder ini.

## Kontrak UI (wajib semua opsi)

- Ujian: `templates/student/exam.html` + `static/css/exam.css` + `static/css/student.css` (Inter, slate/blue).
- Admin: Bootstrap 5.3 + Font Awesome 6.4.
- APK: kiosk + WebView ke URL siswa yang sama (bukan layar soal native).
- Dilarang: Compose soal, Flutter widget soal, SPA yang ganti look.

## Kartu 1–10

### 1 — Kotlin kiosk, backend Python tetap

| | |
|---|---|
| Bahasa baru | **Kotlin** |
| Bahasa tetap | Python, HTML, JS, CSS, SQL, Bash |
| Bahasa hilang | Dart, Flutter engine |
| APK | `android.webkit.WebView` + lock-task |
| Backend | FastAPI seperti sekarang |
| Kekuatan | Strong |
| Ringan | APK |
| Powerful | kiosk native satu module |

Pilih jika: HP siswa lemah, backend jangan disentuh dulu.

### 2 — Go backend, APK Flutter tetap

| | |
|---|---|
| Bahasa baru | **Go** (chi/echo + Asynq/River) |
| Bahasa tetap | Dart/Flutter, Kotlin snippet, HTML, JS, CSS |
| Bahasa hilang | Python produksi (FastAPI, Celery) |
| APK | tidak diubah |
| Backend | Go serve `templates/` + `static/` |
| Kekuatan | Strong |
| Ringan | VPS / lane `api`–`api8` |
| Powerful | goroutine, binary satu file |

Pilih jika: bottleneck server, APK sudah jalan.

### 3 — Go + Kotlin WebView  ← rekomendasi utama

| | |
|---|---|
| Bahasa baru | **Go**, **Kotlin** |
| Bahasa tetap | HTML, JS, CSS, SQL, Bash, Nginx |
| Bahasa hilang | Python produksi, Dart/Flutter |
| APK | Kotlin WebView |
| Backend | Go |
| Kekuatan | Strong |
| Ringan | APK + VPS |
| Powerful | HTTP + kiosk |

Pilih jika: konversi dua runtime, UI tidak boleh berubah.

### 4 — Rust backend, APK Flutter tetap

| | |
|---|---|
| Bahasa baru | **Rust** (Axum/Tower, sqlx) |
| Bahasa tetap | Dart/Flutter, HTML, JS, CSS |
| Bahasa hilang | Python produksi |
| Kekuatan | Worth exploring |
| Ringan | memori server |
| Powerful | safety, latency |

Pilih jika: Go kurang ketat, tim kuat Rust, APK ditunda.

### 5 — Rust + Kotlin WebView

| | |
|---|---|
| Bahasa baru | **Rust**, **Kotlin** |
| Bahasa tetap | HTML, JS, CSS |
| Bahasa hilang | Python, Dart |
| Kekuatan | Worth exploring |
| Risiko | dua rewrite; lebih aman #4 lalu #1 |

Pilih jika: power maksimal, waktu port panjang.

### 6 — Kotlin Ktor + Kotlin WebView

| | |
|---|---|
| Bahasa baru | **Kotlin** (Ktor + Android) |
| Bahasa tetap | HTML, JS, CSS |
| Bahasa hilang | Python produksi, Dart |
| Kekuatan | Worth exploring |
| Ringan | APK ya; VPS tergantung Graal vs JVM |
| Powerful | satu bahasa HTTP + HP |

Pilih jika: tim Android/Kotlin, satu skill set.

### 7 — Elixir/Phoenix + Kotlin WebView

| | |
|---|---|
| Bahasa baru | **Elixir**, **Kotlin** |
| Bahasa tetap | HTML, JS, CSS |
| Bahasa hilang | Python, Dart |
| Kekuatan | Speculative |
| Powerful | BEAM, banyak sesi ujian |

Pilih jika: prioritas concurrency, ops BEAM diterima.

### 8 — Go + HTMX + Kotlin (CSS tidak diganti)

| | |
|---|---|
| Bahasa baru | **Go**, **HTMX**, **Kotlin** |
| Bahasa tetap | HTML, CSS (`exam.css`), SQL |
| Bahasa susut | vanilla `exam-system.js` |
| Kekuatan | Worth exploring |
| Ringan | JS + APK + VPS |
| Powerful | soal/timer/submit di server |
| Syarat | DOM/class tetap agar tampilan sama |

Pilih jika: JS 2972 baris yang ingin dipangkas, look wajib sama.

### 9 — TypeScript Hono/Bun + Kotlin WebView

| | |
|---|---|
| Bahasa baru | **TypeScript**, **Kotlin** |
| Bahasa tetap | HTML, JS klien, CSS |
| Bahasa hilang | Python, Dart |
| Kekuatan | Speculative |
| Powerful | tipe di server |
| Risiko | Node/Bun bukan kontrak VPS sekarang |

Pilih jika: tim TS, Go/Rust tidak mau.

### 10 — Java 21 virtual threads + Graal + Kotlin WebView

| | |
|---|---|
| Bahasa baru | **Java 21**, **Kotlin** |
| Bahasa tetap | HTML, JS, CSS |
| Bahasa hilang | Python, Dart |
| Kekuatan | Speculative |
| Powerful | virtual threads, native image |
| Ringan | sedang (build Graal berat) |

Pilih jika: keluarga JVM end-to-end.

## Tabel cepat

| No | Backend | APK | UI ujian | Hilangkan | Badge |
|---:|---|---|---|---|---|
| 1 | Python | Kotlin WebView | HTML/JS sama | Dart | Strong |
| 2 | Go | Flutter | HTML/JS sama | Python | Strong |
| 3 | Go | Kotlin WebView | HTML/JS sama | Python + Dart | Strong |
| 4 | Rust | Flutter | HTML/JS sama | Python | Worth exploring |
| 5 | Rust | Kotlin WebView | HTML/JS sama | Python + Dart | Worth exploring |
| 6 | Kotlin Ktor | Kotlin WebView | HTML/JS sama | Python + Dart | Worth exploring |
| 7 | Elixir | Kotlin WebView | HTML/JS sama | Python + Dart | Speculative |
| 8 | Go + HTMX | Kotlin WebView | HTML + CSS sama, JS turun | Python + Dart + JS besar | Worth exploring |
| 9 | TypeScript | Kotlin WebView | HTML/JS sama | Python + Dart | Speculative |
| 10 | Java 21 Graal | Kotlin WebView | HTML/JS sama | Python + Dart | Speculative |

## Default jika tidak yakin

**3** (Go + Kotlin, HTML tetap). Langkah aman berjenjang: **1** lalu **2**, hasilnya sama dengan **3**.

## Status

Folder ini hanya dokumen. Coding belum dimulai. Balas nomor 1–10 untuk grilling desain (masih tanpa kode sampai diminta).
