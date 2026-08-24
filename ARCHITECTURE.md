# Arsitektur SIAB1

Dokumen ini membedakan arsitektur produksi yang teramati, komponen opsional yang sudah
tersedia di repository, dan target berikutnya. Basis status saat ini adalah commit `ff3bef9`
dan verifikasi produksi 2026-08-22.

## Pandangan Klien

Android kiosk, Flutter fallback, dan web memakai kontrak HTTP yang sama. Klien tidak memilih
lane, runtime Python atau Go, mode penyimpanan, Redis key, maupun strategi transaksi.

```text
Android kiosk (utama) / Flutter (fallback) / web
                         |
                  HTTPS API SIAB1
                         |
                start, poll, autosave,
                 submit, dan control
```

Adapter HTTP memvalidasi autentikasi, role, payload, serta bukti integritas SEB/SXB. Aturan
sesi, jawaban, locking, idempotensi, final-submit, dan audit harus tetap menjadi satu capability
domain, bukan rangkaian tahap yang dikoordinasikan oleh handler atau klien.

Sketsa boundary target:

```python
class ExamRuntime:
    async def execute(self, command: ExamCommand) -> ExamOutcome:
        """Menjalankan satu operasi ujian lengkap dan idempotent."""
        raise NotImplementedError
```

`ExamCommand` dan `ExamOutcome` adalah tipe domain. `Request`, schema Pydantic, ORM model,
`AsyncSession`, HTTP status, Redis client, dan detail runtime tidak melewati boundary ini.

## Produksi Saat Ini

```text
Cloudflare DNS (DNS-only)
          |
SafeLine (TLS/WAF publik)
          |
127.0.0.1:8080 (loopback-only)
          |
        Nginx
     _____|____________________
    |                          |
student data plane       admin/control plane
api ... api8             api_admin, api_admin2
FastAPI app.main         FastAPI app.main
    |                          |
    +------------+-------------+
                 |
       PgBouncer transaction pool
                 |
           PostgreSQL 15

Redis 7          cache, lock, stream, dan koordinasi runtime
Celery           pekerjaan asinkron dan terjadwal
Prometheus       pengumpulan metrik
Grafana          visualisasi operasional
```

- Seluruh trafik produksi saat ini ditangani FastAPI.
- Nginx memisahkan delapan lane peserta dari dua lane admin/control dan menerapkan limit khusus
  untuk login, join, start, polling, submit, dan monitoring berat.
- Semua lane masih menjalankan modular monolith yang sama dari `app/main.py`. Isolasi yang aktif
  adalah routing, rate limit, worker, dan kapasitas proses; inventory route aplikasi belum
  dipisahkan per plane.
- PgBouncer memakai transaction pooling. Operasi database tidak boleh bergantung pada state
  koneksi yang bertahan di luar satu transaksi.
- PostgreSQL adalah source of truth. Redis menyimpan state turunan, cache, lock, stream,
  koordinasi, dan buffer opsional; kehilangan Redis tidak boleh menghilangkan jawaban yang telah
  diakui durable.
- SafeLine adalah satu-satunya ingress publik. Nginx origin tidak diekspos langsung ke internet.

## Komponen Opsional

### Go Native-Lean

`go_server` dan `go_worker` tersedia di Compose melalui profile `native-lean`, tetapi tidak aktif
di VPS dan bukan upstream Nginx produksi. Go saat ini berstatus **implemented/optional**, bukan
**canary**, **production**, atau **primary**.

Go tidak boleh disebut menangani trafik produksi sampai routing Nginx, container aktif, revision,
health, contract parity, metrik, dan hasil rekonsiliasi membuktikannya. Broad proxy fallback dari
Go ke Python, request-level runtime switching, dan dual-write jawaban tidak menjadi target.

### Read Replica

`db_replica` tersedia melalui profile `scaling` dan tidak termasuk topologi produksi default.
Aktivasi membutuhkan bukti kebutuhan read scaling, routing query read yang terverifikasi, serta
runbook failover dan recovery.

## Target Berikutnya

Target terdekat adalah **plane-aligned FastAPI modular monolith**, bukan migrasi bahasa atau
microservices langsung.

```text
SafeLine -> Nginx
  -> student FastAPI composition -> ExamRuntime
  -> control FastAPI composition -> control capabilities + ExamRuntime

ExamRuntime
  -> PostgreSQL adapter -> PgBouncer -> PostgreSQL
  -> Redis adapter -> cache/lock/stream/coordination
  -> post-commit monitoring events
```

- Buat composition root student yang hanya memuat route dan middleware data plane.
- Buat composition root control yang memuat admin, guru, Pengawas, monitoring, export, dan
  operasi sistem.
- Gunakan satu implementasi domain `ExamRuntime` untuk kedua plane agar policy sesi, integritas,
  answer merge, locking, final-submit, scoring, dan audit tidak bercabang.
- Pertahankan satu image, satu repository, satu schema, PostgreSQL, dan Redis pada VPS saat ini.
  Pemisahan ini adalah boundary proses dan capability, bukan distributed microservices.
- Pertahankan kontrak HTTP yang ada melalui adapter tipis. Migrasi dilakukan satu operasi lengkap
  per tahap dan harus tetap dapat dikembalikan ke `app.main:app`.

Boundary ini dipilih karena menyembunyikan kompleksitas konsistensi ujian di balik satu interface
kecil. Alternatif hybrid Go/FastAPI ditolak sebagai langkah langsung karena menambah kontrak
lintas bahasa, RPC internal, write-owner switching, dan risiko rollback sebelum bottleneck Python
terukur. Ide yang dipertahankan dari alternatif tersebut adalah contract fixture lintas runtime,
canary per sesi, larangan dual-write, dan rollback melalui routing yang deterministik.

## Gerbang Performa dan Go

Tidak ada runtime yang boleh diklaim lebih cepat berdasarkan jumlah worker, container sehat,
bahasa implementasi, atau unit test. Promosi Go hanya dipertimbangkan untuk bottleneck yang telah
diukur dan harus melewati seluruh gerbang berikut:

1. Backup otomatis tersedia dan restore drill berhasil.
2. Revision deployment dapat dibuktikan dan restart policy disetujui.
3. Baseline Python memakai concurrency, request mix, burst shape, dan SLO yang disepakati.
4. Contract parity mencakup auth, role, SEB/SXB, status/error body, retry, dan idempotensi.
5. Rekonsiliasi membuktikan nol jawaban hilang, nol cross-session write, dan final-submit konsisten.
6. Failure test mencakup Redis, PgBouncer, replica runtime, dan rollback.
7. Kandidat tidak memiliki error rate lebih tinggi atau regresi latency material dan menunjukkan
   manfaat terukur, misalnya CPU per request lebih rendah atau throughput berkelanjutan lebih
   tinggi pada SLO yang sama.
8. Canary merutekan sesi secara utuh, tidak membagi request satu sesi ke writer berbeda.
9. Rollback ke Python berhasil tanpa schema rollback, data repair, atau dual-write.

## Klien

### Android Kiosk

`android-kiosk/` adalah klien utama dengan package ID `id.siab1.kiosk`. Release memakai
`SIAB1_SERVER_URL`, menolak placeholder, dan membutuhkan signing credential dari environment.

Kiosk membatasi WebView dan header injection ke origin server, memakai secure flags, menyimpan
answer journal untuk recovery, serta membedakan lock state `LOCKED`, `PINNED`, dan `NONE`.
Perangkat BYOD tanpa device-owner dapat melanjutkan dengan peringatan proteksi terbatas dan retry;
keadaan tersebut tidak disamakan dengan kiosk terkelola penuh.

### Flutter Fallback

`flutter_client_code/` dipertahankan sebagai fallback dengan application ID `id.siab1.flutter`.

### Web

Template admin dan peserta berada di `templates/`. Asset modular berada di `static/`; bundle
terdaftar di `scripts/frontend_bundle_registry.csv` dan diverifikasi reproducible.

## Integritas Asesmen

- Validasi SEB/SXB, signature policy, dan origin-bound WebView bridge.
- JWT, role enforcement, rate limiting, CAPTCHA, dan account lockout.
- Autosave, answer journal, final-submit guard, recovery, dan audit trail.
- Security headers, sanitization, violation scoring, dan pemisahan control/data plane.
- Pengawas bersifat read-only untuk publish, unpublish, dan regenerasi token; guard otorisasi
  dijalankan sebelum akses database.

## Update `ff3bef9`

Update ini memperkeras boundary yang sudah ada tanpa mengubah topologi produksi:

- Pengawas tidak dapat publish, unpublish, atau regenerasi token, baik dari UI maupun API.
- Handler API mempertahankan detail domain untuk token ujian yang tidak valid.
- SEB Legacy tidak memuat bundle/API saat feature flag dimatikan.
- Modal zoom gambar memiliki lifecycle accessibility yang benar.
- Android kiosk menangani kegagalan lock task dan fallback BYOD secara eksplisit.
- Versi Android dinaikkan menjadi `2.0.2+4`; artifact signed belum diterbitkan karena signing
  material belum tersedia.

Validasi update: 495 test Python lulus, targeted security/UI/native tests lulus, Kotlin compile
dan lint lulus, CI production hardening sukses, serta seluruh lane produksi sehat setelah rolling
restart. Bukti ini menunjukkan regression health, bukan peak capacity.

## Risiko Operasional

- Controlled public load 50/200/620 lulus correctness gate, tetapi synchronized burst masih
  menghasilkan latency p95 tinggi dan harus dipantau saat gelombang nyata.
- Backup harian, restore drill mingguan, dan guarded stateless restart telah aktif. Jadwal
  restart memiliki horizon terbatas dan harus diperpanjang sebelum habis.
- Public exam flow, upload, dan violation/WebSocket smoke lulus. Heavy export tetap sengaja
  dinonaktifkan pada peak mode; success-path memerlukan maintenance window.
- Android `2.0.2+4` masih menunggu signing material dan physical-device smoke.
- Perubahan ownership atau runtime tidak boleh dilakukan saat ujian aktif.

Bukti agregat tersedia di
[docs/production-readiness-2026-08-24.md](docs/production-readiness-2026-08-24.md).

## Entry Point

- FastAPI: `app/main.py`
- Go API opsional: `go/cmd/server/main.go`
- Go worker opsional: `go/cmd/worker/main.go`
- Android: `android-kiosk/app/src/main/java/id/siab1/kiosk/`
- Flutter: `flutter_client_code/lib/main.dart`
- Compose: `docker-compose.production.yml`
- Nginx: `docker/nginx.production.conf`
