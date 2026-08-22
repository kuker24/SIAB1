# Deployment SIAB1

Dokumen ini adalah kontrak deployment untuk VPS baru. Domain publik belum ditetapkan; jangan melakukan cutover sebelum DNS, TLS, CORS, dan URL client disepakati.

## Prasyarat

- Docker Engine dan Docker Compose plugin.
- Domain dan certificate origin yang valid.
- File `.env` production di luar version control.
- Backup dan rollback plan yang telah diuji.
- Kapasitas host yang divalidasi terhadap beban target.

## Identitas Runtime

- Compose project: `siab1`
- Database: `siab1`
- API image: `siab1-api`
- Go image: `siab1-go`
- Lokasi yang direkomendasikan: `/opt/siab1`
- Override lokasi untuk host-control: `SIAB1_HOME`

## Konfigurasi Wajib

Salin `.env.example` menjadi `.env` di host dan isi nilainya melalui secret manager atau prosedur aman. Jangan commit hasilnya.

Nilai minimum mencakup:

```env
APP_ENV=production
DEBUG=false
DATABASE_URL=postgresql+asyncpg://examuser:<password>@pgbouncer:6432/siab1
POSTGRES_DB=siab1
DB_PASSWORD=<secret>
SECRET_KEY=<secret>
JWT_SECRET_KEY=<secret>
SEB_DEFAULT_CONFIG_KEY=<secret>
SEB_DEFAULT_BROWSER_EXAM_KEY=<secret>
CORS_ORIGINS=["https://your-domain.example"]
```

File certificate Cloudflare Origin ditempatkan di `docker/certs/` dan tetap di luar Git.

## Validasi Sebelum Start

```bash
python scripts/check_security.py
pytest -q
SKIP_HTTP=1 bash scripts/verify_release_gate.sh
docker compose -p siab1 -f docker-compose.production.yml config --quiet
```

## Start

```bash
docker compose -p siab1 -f docker-compose.production.yml up -d
docker compose -p siab1 -f docker-compose.production.yml ps
```

Periksa `/health`, login admin, login peserta, SXB rejection/acceptance, autosave, final submit, dan export sebelum membuka trafik umum.

## Client Release

Native Android release membutuhkan:

```bash
export SIAB1_SERVER_URL=https://your-domain.example/
export SIAB1_RELEASE_KEYSTORE=/secure/path/release.jks
export SIAB1_RELEASE_STORE_PASSWORD=<secret>
export SIAB1_RELEASE_KEY_ALIAS=<alias>
export SIAB1_RELEASE_KEY_PASSWORD=<secret>
bash tools/build_native_kiosk_apk.sh
```

Jangan merilis client yang masih menunjuk `siab1.invalid`.

## Backup dan Rollback

Gunakan script di `bin/` untuk backup dan restore. Validasi hasil backup sebelum perubahan. Jangan pernah menjalankan `docker compose down -v` pada data production tanpa approval eksplisit dan backup terverifikasi.

## Domain Pending

Ketika domain baru tersedia, perbarui:

- DNS dan Cloudflare/TLS.
- Nginx `server_name` dan certificate.
- `CORS_ORIGINS` serta public monitoring URL.
- `SIAB1_SERVER_URL` untuk semua client release.
- Smoke test dan GitHub homepage metadata.
