# SIAB1

[![Production hardening checks](https://github.com/kuker24/SIAB1/actions/workflows/production-hardening.yml/badge.svg)](https://github.com/kuker24/SIAB1/actions/workflows/production-hardening.yml)

**Sistem Informasi Asesmen Berintegritas** untuk penyelenggaraan asesmen digital yang terlindungi, terpantau, dan dapat diaudit.

SIAB1 menggabungkan aplikasi kiosk Android, runtime FastAPI, PostgreSQL, Redis, Celery,
serta kontrol SEB/SXB untuk menjaga integritas sesi asesmen dari login sampai pelaporan. Runtime
Go Native-Lean tersedia sebagai komponen opsional dan belum menerima trafik produksi.

## Kemampuan Utama

- Aplikasi kiosk Android native dengan pembatasan navigasi, screenshot protection, dan origin-bound authentication.
- Manajemen peserta, bank soal, jadwal, sesi, penilaian, analitik, dan laporan.
- Autosave, answer journal, final-submit integrity, reconnect, dan recovery sesi.
- Validasi SEB/SXB, signature policy, rate limiting, CAPTCHA, account lockout, dan audit logging.
- Monitoring real-time, Prometheus, Grafana, alerting, backup, dan recovery tooling.
- FastAPI sebagai runtime produksi dengan jalur Go Native-Lean opsional yang harus melewati
  contract, load, canary, dan rollback gates sebelum dipromosikan.

## Arsitektur

```text
Android kiosk / browser / Flutter fallback
                    |
             SafeLine -> Nginx
                    |
      FastAPI student + control lanes
                    |
             PgBouncer / Redis
                    |
          PostgreSQL / Celery workers
```

Status produksi, komponen opsional, dan target boundary tersedia di
[ARCHITECTURE.md](ARCHITECTURE.md).

## Struktur Repository

| Path | Fungsi |
|---|---|
| `android-kiosk/` | Klien Android native utama |
| `app/` | API, policy, model, service, middleware, dan task FastAPI |
| `go/` | Kandidat runtime Go Native-Lean opsional; bukan upstream produksi |
| `flutter_client_code/` | Klien Flutter fallback |
| `templates/`, `static/` | Antarmuka web admin dan peserta |
| `docker/`, `monitoring/` | Container, Nginx, PgBouncer, Prometheus, dan Grafana |
| `scripts/`, `bin/` | Verifikasi, maintenance, backup, recovery, dan observability |
| `tests/` | Regression dan security contract tests |
| `docs/` | Runbook dan checklist aktif |

## Pengembangan Lokal

Persyaratan utama: Python 3.11+, PostgreSQL, dan Redis.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

Alternatif:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Verifikasi

```bash
python -m compileall app
python scripts/check_security.py
pytest -q
SKIP_HTTP=1 bash scripts/verify_release_gate.sh
```

Untuk Go:

```bash
cd go
go test ./...
go vet ./...
go build ./...
```

Untuk Android kiosk:

```bash
cd android-kiosk
./gradlew :app:compileDebugKotlin :app:lintDebug
```

## Deployment

Deployment production menggunakan `docker-compose.production.yml`. Database, image, dan Compose project memakai slug `siab1`. Hostname publik adalah `siab.man1rokanhulu.cloud`; SafeLine menangani ingress dan TLS sebelum meneruskan trafik ke origin Nginx yang hanya terikat ke loopback.

Lihat [DEPLOYMENT.md](DEPLOYMENT.md). Jangan menjalankan rebuild, migrasi, atau penghapusan volume ketika asesmen aktif.

## Dokumentasi

- [Arsitektur](ARCHITECTURE.md)
- [Deployment](DEPLOYMENT.md)
- [Indeks runbook](docs/README.md)
- [Riwayat ringkas](docs/HISTORY.md)

## Keamanan

Jangan commit `.env`, keystore, certificate, private key, token, hasil asesmen, upload peserta, atau credential lainnya. Laporkan kerentanan secara privat kepada maintainer, bukan melalui issue publik.
