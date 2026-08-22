# Deployment SIAB1

Kontrak production saat ini menggunakan `siab.man1rokanhulu.cloud` dengan SafeLine CE sebagai WAF dan terminator TLS. Cloudflare tetap menjadi authoritative DNS, tetapi record SIAB1 memakai mode DNS-only.

## Topologi

```text
Internet -> SafeLine :80/:443 -> 127.0.0.1:8080 -> Nginx SIAB1 -> API
```

- SafeLine dan SIAB1 berjalan pada VPS yang sama.
- SafeLine adalah satu-satunya ingress HTTP/HTTPS publik.
- Origin SIAB1 harus tetap bind ke loopback.
- Dashboard SafeLine harus tetap bind ke loopback dan diakses melalui SSH tunnel.
- Pangolin tidak diperlukan selama origin SIAB1 berada pada VPS ini.

## Prasyarat

- Docker Engine dan Docker Compose plugin.
- DNS `siab.man1rokanhulu.cloud` mengarah ke VPS setelah origin siap.
- Sertifikat publik yang valid dikelola pada SafeLine.
- File `.env` production berada di luar version control.
- Backup dan rollback plan telah diuji sebelum data production dimigrasikan.
- Host memiliki firewall aktif dan swap untuk emergency memory pressure.

## Identitas Runtime

- SafeLine directory: `/opt/safeline`
- SIAB1 directory: `/opt/siab1`
- SafeLine release: `9.4.0`
- SafeLine management: `127.0.0.1:9443`
- SIAB1 origin: `127.0.0.1:8080`
- Compose project SIAB1: `siab1`
- Database SIAB1: `siab1`

## Konfigurasi SIAB1

Salin `.env.example` menjadi `.env` pada host dan isi melalui prosedur secret management. Jangan commit hasilnya.

Nilai minimum mencakup:

```env
APP_ENV=production
DEBUG=false
FORCE_HTTPS=true
DOMAIN=siab.man1rokanhulu.cloud
PROTOCOL=https
CORS_ORIGINS=https://siab.man1rokanhulu.cloud
DATABASE_URL=postgresql+asyncpg://examuser:<password>@pgbouncer:6432/siab1
POSTGRES_DB=siab1
DB_PASSWORD=<secret>
SECRET_KEY=<secret>
JWT_SECRET_KEY=<secret>
SEB_DEFAULT_CONFIG_KEY=<secret>
SEB_DEFAULT_BROWSER_EXAM_KEY=<secret>
```

TLS tidak dikonfigurasi pada Nginx SIAB1. SafeLine meneruskan `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Host`, dan `X-Forwarded-Proto` yang telah dinormalisasi.

## Konfigurasi SafeLine

Template Compose yang telah dipin tersedia di `infrastructure/safeline/`. File `.env` SafeLine hanya dibuat pada VPS dengan permission `0600`.

Konfigurasi aplikasi melalui dashboard:

| Field | Value |
|---|---|
| Domain | `siab.man1rokanhulu.cloud` |
| Upstream | `http://127.0.0.1:8080` |
| Public ports | `80`, `443` |
| WebSocket | Enabled |
| Upload limit | At least `100 MB` |
| Upstream timeout | At least `300 seconds` |
| Certificate | Public Let's Encrypt certificate |

Mulai dengan protection mode yang seimbang. Jangan aktifkan JavaScript challenge pada API atau kiosk. Hindari rate limit agresif per-IP karena banyak peserta dapat berbagi satu NAT sekolah.

Dashboard diakses dari workstation melalui tunnel:

```bash
ssh -N -L 9443:127.0.0.1:9443 siab1
```

Kemudian buka `https://127.0.0.1:9443`. Jangan membuka TCP `9443` pada firewall.

## DNS Cloudflare

Nameserver registrar tetap `bonnie.ns.cloudflare.com` dan `curt.ns.cloudflare.com`. Jangan mengubah nameserver di DomaiNesia.

Setelah pengujian origin lulus, buat record berikut di Cloudflare:

| Type | Name | Target | Proxy status | TTL |
|---|---|---|---|---|
| `A` | `siab` | IP VPS SIAB1 | DNS only | Auto |

Jangan mengubah record root, `www`, MX, atau TXT saat cutover SIAB1. Mode DNS-only mengekspos IP VPS dan tidak memberikan proxy/DDoS protection Cloudflare.

## Validasi Sebelum Start

```bash
python scripts/check_security.py
pytest -q
SKIP_HTTP=1 bash scripts/verify_release_gate.sh
docker compose -p siab1 -f docker-compose.production.yml config --quiet
SAFELINE_DIR=/opt/safeline POSTGRES_PASSWORD=not-a-production-secret \
  SUBNET_PREFIX=192.168.236 docker compose \
  -f infrastructure/safeline/docker-compose.yml config --quiet
```

## Start SIAB1

```bash
docker compose -p siab1 -f docker-compose.production.yml up -d
docker compose -p siab1 -f docker-compose.production.yml ps
curl --fail --header 'Host: siab.man1rokanhulu.cloud' http://127.0.0.1:8080/health
```

Periksa health, login admin, login peserta, SXB rejection/acceptance, autosave, final submit, WebSocket, upload, dan export sebelum membuka trafik umum.

## Client Release

Native Android release membutuhkan:

```bash
export SIAB1_SERVER_URL=https://siab.man1rokanhulu.cloud/
export SIAB1_RELEASE_KEYSTORE=/secure/path/release.jks
export SIAB1_RELEASE_STORE_PASSWORD=<secret>
export SIAB1_RELEASE_KEY_ALIAS=<alias>
export SIAB1_RELEASE_KEY_PASSWORD=<secret>
bash tools/build_native_kiosk_apk.sh
```

Jangan merilis client yang masih menunjuk `siab1.invalid`.

## Backup dan Rollback

Gunakan script di `bin/` untuk backup dan restore SIAB1. Backup SafeLine mencakup `/opt/safeline/.env`, database SafeLine, dan resource directory. Validasi hasil backup sebelum perubahan. Jangan pernah menjalankan `docker compose down -v` pada data production tanpa approval eksplisit dan backup terverifikasi.
