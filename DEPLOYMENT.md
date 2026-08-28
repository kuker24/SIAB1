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
sudo bash scripts/prepare_runtime_dirs.sh /opt/siab1
docker compose -p siab1 -f docker-compose.production.yml up -d
docker compose -p siab1 -f docker-compose.production.yml ps
curl --fail --header 'Host: siab.man1rokanhulu.cloud' http://127.0.0.1:8080/health
```

Fresh database tidak membuat akun privileged bawaan. Bootstrap admin pertama dengan
password satu kali dari terminal operator, lalu hapus variabelnya dari sesi shell:

```bash
read -rsp 'Initial admin password: ' SIAB1_BOOTSTRAP_ADMIN_PASSWORD
export SIAB1_BOOTSTRAP_ADMIN_PASSWORD
docker compose -p siab1 -f docker-compose.production.yml run --rm \
  -e SIAB1_BOOTSTRAP_ADMIN_PASSWORD api python scripts/bootstrap_admin.py
unset SIAB1_BOOTSTRAP_ADMIN_PASSWORD
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

Pasang backup harian pukul 01:30 WIB dan restore drill non-destruktif mingguan:

```bash
sudo bash scripts/install_backup_systemd.sh /opt/siab1
sudo systemctl start siab1-backup.service
sudo systemctl start siab1-restore-drill.service
sudo systemctl status siab1-backup.timer siab1-restore-drill.timer
```

Setiap archive `recovery_sistem/backup_*.tar.gz` memiliki sidecar SHA-256. Restore drill
memvalidasi checksum dan memulihkan database ke database sementara, lalu menghapus database
sementara tersebut tanpa mengganti database `siab1`.

Karena deployment VPS berbasis file, buat bukti release setelah sinkronisasi file.
Source release identity bukan runtime filesystem identity.

Fingerprint source yang sama dipakai di Git checkout dan pohon staging:

```bash
bash scripts/source_release_fingerprint.sh
```

Full release:

```bash
sudo OUTPUT_DIR=/opt/siab1/releases \
  RELEASE_MODE=full \
  SOURCE_GIT_SHA=<git-commit> \
  DEPLOYMENT_DESTINATION=/opt/siab1 \
  BACKUP_PATH=<backup.tar.gz> \
  BACKUP_SHA256=<backup-sha256> \
  bash scripts/generate_release_manifest.sh <git-commit>
```

Delta release (jangan dilabeli sebagai full-tree commit identity):

```bash
sudo OUTPUT_DIR=/opt/siab1/releases \
  RELEASE_MODE=delta \
  SOURCE_GIT_SHA=<git-commit> \
  DEPLOYED_PATHS_FILE=/tmp/deployed-paths.txt \
  DEPLOYMENT_DESTINATION=/opt/siab1 \
  bash scripts/generate_release_manifest.sh <release-id>
```

Metadata mencatat source SHA, mode full/delta, fingerprint source, checksum file terdeploy,
identitas Compose/Nginx, dan referensi backup/rollback. Certificate, upload, live canary,
backup `.bak`, dan artifact build dinamis dikecualikan.

## GitHub governance

`main` memerlukan pull request. Direct push, force-push, dan penghapusan `main` diblokir.
Check wajib: `validate` (`Production hardening checks`). Tag `stable-*` tidak boleh dihapus
atau dipindah. Rollback production memakai fallback per-route atau artifact sebelumnya,
bukan `git reset` pada `main`. Kebijakan lengkap: `docs/github-governance.md`.
