# Arsitektur SIAB1

SIAB1 adalah platform asesmen digital dengan Android kiosk sebagai klien utama, Flutter sebagai fallback, dan dua runtime backend yang berbagi PostgreSQL serta Redis.

## Runtime

- **Nginx** menerima trafik publik dan memisahkan jalur peserta dari jalur admin/control.
- **Go** menangani route native yang telah memiliki parity dan sesuai untuk trafik utama.
- **FastAPI** menyediakan runtime lengkap serta fallback untuk fitur yang belum atau tidak tepat dipindahkan ke Go.
- **PgBouncer** membatasi tekanan koneksi ke PostgreSQL.
- **Redis** menyimpan cache, lock, stream monitoring, dan koordinasi runtime.
- **Celery** menjalankan pekerjaan asinkron dan terjadwal.

## Boundary Backend

Native handler digunakan ketika dependency database/JWT tersedia. FastAPI tetap menjadi fallback untuk operasi Redis-heavy, upload/filesystem, PDF/DOCX/Excel, APK/SEB toolchain, Telegram, backup/GPG, host metrics, Docker/privileged operation, serta mutasi settings lintas runtime.

Kedua runtime harus mempertahankan schema, status code, auth, SXB policy, dan response contract yang sama.

## Klien

### Android Kiosk

`android-kiosk/` adalah klien utama. Package ID adalah `id.siab1.kiosk`. Server release diberikan melalui `SIAB1_SERVER_URL`; build release menolak placeholder dan membutuhkan signing credential dari environment.

### Flutter Fallback

`flutter_client_code/` dipertahankan untuk fallback. Application ID adalah `id.siab1.flutter`, sehingga tidak bertabrakan dengan native kiosk.

### Web

Template admin dan peserta berada di `templates/`. Asset modular berada di `static/`; bundle terdaftar di `scripts/frontend_bundle_registry.csv` dan diverifikasi reproducible.

## Integritas Asesmen

- Validasi SEB/SXB dan signature policy.
- JWT, role enforcement, rate limiting, CAPTCHA, dan account lockout.
- Autosave, answer journal, final-submit guard, recovery, dan audit trail.
- Origin-bound WebView bridge dan header injection pada Android kiosk.
- Security headers, sanitization, dan violation scoring.

## Data

Database production baru bernama `siab1`. Perubahan tulis memakai dependency transaksi write; query read memakai dependency read. Jangan mengganti schema atau menghapus volume tanpa backup terverifikasi.

## Entry Point

- FastAPI: `app/main.py`
- Go API: `go/cmd/server/main.go`
- Go worker: `go/cmd/worker/main.go`
- Android: `android-kiosk/app/src/main/java/id/siab1/kiosk/`
- Flutter: `flutter_client_code/lib/main.dart`
- Compose: `docker-compose.production.yml`
