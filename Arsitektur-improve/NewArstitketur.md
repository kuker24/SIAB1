# SIAB1 Native-Lean v2 — NewArsitiktur

Keputusan terkunci. **Belum ada ubah kode.** Fungsi tetap sama. UI tetap sama.

Fondasi: **#3** dari `arstikteturnew.md`, versi lebih ekstrem dalam penyederhanaan.

Nama arsitektur: **#3+ Go Modular Monolith + Kotlin Native Kiosk + HTML Renderer**

Baca bersama: `improvearsitektur.md`, `arstikteturnew.md`.

---

## Satu kalimat

Go = core server. Kotlin = kiosk perangkat. HTML/CSS = renderer soal satu-satunya. JS = interaksi browser tipis, pecah module. Flutter/Dart/CPython/Celery hilang.

---

## Kontrak yang tidak pecah

- Fungsi ujian, admin, autosave, audit, SXB/SEB, rate limit, lockout, CAPTCHA, JWT ujian 120 menit — **sama**.
- Tampilan admin Bootstrap 5.3 + Font Awesome; ujian Inter + `exam.css` / `student.css` — **sama**.
- Satu renderer soal: HTML di browser PC **dan** di WebView APK. Kotlin **tidak** merender soal.
- Lima lane tetap: HTTP, browser UI, exam client kiosk, data (PostgreSQL + Redis), ops (Nginx/Docker/Bash).
- Delapan lane siswa + dua lane admin di Nginx — **sama**.
- Bukan microservice. Bukan HTMX sebagai dependency kritikal. Bukan Jetpack Compose soal. Bukan Flutter Web.

---

## Diagram target

```text
                    NGINX
                      │
          ┌───────────▼───────────┐
          │      GO CORE          │
          │  net/http + chi       │
          │                       │
          │ Auth / Exam / Admin   │
          │ Autosave / Audit      │
          │ Rate Limit / SXB      │
          └───────┬───────┬───────┘
                  │       │
            PostgreSQL   Redis
                  │
          ┌───────▼────────┐
          │ HTML/CSS/JS    │
          │ Exam Renderer  │
          │ SATU SAJA      │
          └───────┬────────┘
                  │ HTTPS
        ┌─────────▼──────────┐
        │ ANDROID KOTLIN     │
        │ Native Kiosk Shell │
        │                    │
        │ WebView            │
        │ LockTask           │
        │ FLAG_SECURE        │
        │ Network monitor    │
        │ JS Bridge minimal  │
        └────────────────────┘
```

Peran:

```text
GO       = business / core / server
KOTLIN   = device / security / kiosk
HTML/CSS = visual renderer
JS       = browser interaction tipis
POSTGRES = durable state
REDIS    = ephemeral / session / cache / queue
NGINX    = edge / routing
```

---

## Yang berubah vs sekarang

| Sekarang | Baru |
| --- | --- |
| Python FastAPI | **Go** (`net/http` + chi) |
| Celery | **Go worker ringan / Redis queue** |
| Flutter + Dart | **hapus total** |
| Kotlin hanya pembantu Flutter | **Kotlin = APK utama** |
| Flutter `InAppWebView` | **Android `WebView` langsung** |
| Python + Dart + Kotlin + JS | **Go + Kotlin + HTML/JS** |
| banyak runtime | **2 runtime utama** (Go, Kotlin) + HTML di browser |
| `exam-system.js` ~2972 baris monolit | **pecah module kecil** |
| deploy dependency Python | **Go binary** |

Hilang:

```text
Flutter ──────── X
Dart ─────────── X
CPython runtime  X
Celery runtime ─ X
```

Tetap:

```text
Go ──────────── ✓
Kotlin native ─ ✓
HTML renderer ─ ✓
Postgres ────── ✓
Redis ───────── ✓
Nginx ───────── ✓
```

---

## Backend: modular monolith, bukan microservice

**Jangan:**

```text
auth-service
exam-service
student-service
audit-service
worker-service
...
```

Alasan: hop jaringan, RAM, deploy, dan titik gagal bertambah. SIAB1 tidak butuh itu.

**Pakai** satu pohon sumber, **maksimum 2 proses native**:

```text
siab1-server
siab1-worker
```

Layout:

```text
siab1/
├── cmd/
│   ├── server/
│   └── worker/
├── internal/
│   ├── exam/
│   ├── auth/
│   ├── student/
│   ├── admin/
│   ├── security/
│   ├── audit/
│   └── persistence/
├── templates/
└── static/
```

- `templates/` dan `static/` boleh di-`embed` ke binary.
- Satu binary server: Auth / Exam / Admin / Autosave / Audit / Rate limit / SXB.
- Worker: antrian Redis (pengganti Celery), bukan proses Python.
- Module di `internal/` adalah pemisahan paket Go, **bukan** service jaringan.

---

## Android: native kiosk, bukan renderer soal

```text
Kotlin
  ↓
Activity
  ↓
Native Security / Kiosk Layer
  ↓
WebView
  ↓
exam.html
```

Kotlin memegang:

- lock task
- `FLAG_SECURE`
- lifecycle
- network state
- reconnect trigger
- download blocking
- external-app blocking
- clipboard policy
- screenshot policy
- WebView policy
- JS bridge (minimal)

Kotlin **tidak** merender soal. Compose full untuk soal = renderer kedua = ditolak.

JS bridge tipis: kiosk/security/reconnect saja, bukan logika soal.

---

## JS ujian: pecah module, bukan HTMX penuh

Tidak dipilih: `Go + HTMX + Kotlin` sebagai jalur kritikal.

Alasan: autosave, reconnect, SEB/SXB, dan jaringan siswa adalah jalur ujian. HTMX belum diuji di jalur itu.

Dipilih:

```text
Go
+
Vanilla JS modular tipis
+
Kotlin native
```

Pecah `exam-system.js` (bukan ganti tampilan):

```text
exam/
├── core.js
├── navigation.js
├── timer.js
├── autosave.js
├── reconnect.js
├── security.js
└── bridge.js
```

CSS/DOM/`exam.css` tetap. Ini mengambil ide “JS mengecil” dari opsi #8 **tanpa** dependency HTMX.

---

## Runtime dan bahasa

| Lapisan | Bahasa / runtime | Catatan |
| --- | --- | --- |
| HTTP core | Go, chi, `net/http` | ganti FastAPI |
| Worker | Go + Redis queue | ganti Celery |
| APK | Kotlin, Android WebView | ganti Flutter/Dart |
| Renderer | HTML + CSS | tidak diganti |
| Interaksi browser | Vanilla JS modular | pecah, bukan framework |
| Data | PostgreSQL | tidak diganti |
| Ephemeral | Redis | session / cache / queue |
| Edge | Nginx | lane tetap |

Dua runtime utama produksi klien/server: **Go** dan **Kotlin**. Browser tetap HTML/JS. Data plane bukan “bahasa aplikasi”.

---

## Migrasi (nanti, masih bukan coding hari ini)

Paling aman: **Kotlin native dulu → lalu Go**.

1. **Fase A = #1** — APK Kotlin WebView, backend Python tetap. UI HTML sama. Flutter hilang.
2. **Fase B = #2** — HTTP lane Go, APK sudah Kotlin. Template/static sama.
3. **Hasil = #3+** — sama dengan target ini, blast radius lebih kecil per fase.

Jangan ganti renderer. Jangan pecah microservice di tengah jalan. Jangan masukkan HTMX ke jalur autosave sebelum tes SEB.

Parity wajib sebelum cutover: autosave, reconnect, SXB/SEB, JWT 120, kiosk, audit, tampilan pixel-familiar.

---

## Mapping file sekarang → target (acuan, bukan kerja kode)

| Sekarang | Target |
| --- | --- |
| `app/main.py`, `app/api/`, `app/core/` | `cmd/server` + `internal/*` |
| `app/tasks/` Celery | `cmd/worker` |
| `templates/`, `static/` | `templates/`, `static/` (embed boleh) |
| `static/js/exam-system.js` | `static/js/exam/*.js` |
| `flutter_client_code/lib/pages/exam_page.dart` | Kotlin Activity + WebView |
| `MainActivity.kt` (MethodChannel Flutter) | Kotlin kiosk native, bukan `FlutterActivity` |
| `docker-compose.production.yml` | image Go binary + worker; APK Kotlin |

---

## Ditolak secara eksplisit

- Microservice per domain
- HTMX sebagai tulang ujian
- Jetpack Compose / Flutter widget untuk soal
- React / Vue / Svelte yang ganti look
- Ganti PostgreSQL atau Redis
- Memendekkan JWT ujian
- Mengubah urutan kebijakan keamanan (SXB, rate limit, header)

---

## Status

Dokumen keputusan. Coding belum dimulai. Target arsitektur: **SIAB1 Native-Lean v2 (#3+)**.
