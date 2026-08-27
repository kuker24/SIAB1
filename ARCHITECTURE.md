# Arsitektur SIAB1

Dokumen ini membedakan arsitektur produksi yang teramati, komponen opsional yang sudah
tersedia di repository, dan target berikutnya. Basis status saat ini adalah closeout
student hot-path `2856e47` (Go image `siab1-go:373c131`) dan verifikasi VPS 2026-08-28.

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
     _____|______________________________________
    |                     |                      |
student hot-path     student non-hot-path   admin/control
go_server            api ... api8           api_admin, api_admin2
join/start/answer    FastAPI app.main       FastAPI app.main
autosave/batch/submit  (fallback for the six)
    |                     |                      |
    +---------------------+----------------------+
                          |
               PgBouncer transaction pool
                          |
                    PostgreSQL 15

Redis 7          cache, lock, stream, dan koordinasi runtime
Celery           pekerjaan asinkron dan terjadwal
Prometheus       pengumpulan metrik
Grafana          visualisasi operasional
```

- Enam rute siswa (join, start, submit-answer, auto-save, auto-save-batch, submit) dirutekan
  100% ke `go_start_backend` (`go_server:8000`, replica `go-start`). FastAPI tetap map default
  dan `server api:8000 resolve backup`.
- Login, poll, export, admin, guru, Pengawas, dan sisa API tetap FastAPI (`api`…`api8` plus
  `api_admin` / `api_admin2`).
- Nginx memisahkan lane peserta dari lane admin/control dan menerapkan limit khusus untuk login,
  join, start, polling, submit, dan monitoring berat.
- Satu sesi punya satu writer. Dual-write jawaban ke Go dan FastAPI dilarang. Rollback adalah
  swap file canary per rute di `runtime_control/`, bukan `docker compose down -v`.
- PgBouncer memakai transaction pooling. Operasi database tidak boleh bergantung pada state
  koneksi yang bertahan di luar satu transaksi.
- PostgreSQL adalah source of truth. Redis menyimpan state turunan, cache, lock, stream,
  koordinasi, dan buffer; kehilangan Redis tidak boleh menghilangkan jawaban yang telah
  diakui durable.
- SafeLine adalah satu-satunya ingress publik. Nginx origin tidak diekspos langsung ke internet.

## Komponen Opsional

### Go worker dan Compose profile

`go_server` produksi berjalan sebagai image `siab1-go:373c131`. Repo Compose masih menandai
service itu di profile `native-lean`; komentar profile bukan topologi live.

`go_worker` tetap opsional dan bukan bagian closeout hot-path. Jangan mengaktifkannya tanpa
bukti kebutuhan dan runbook.

### Read Replica

`db_replica` tersedia melalui profile `scaling` dan tidak termasuk topologi produksi default.
Aktivasi membutuhkan bukti kebutuhan read scaling, routing query read yang terverifikasi, serta
runbook failover dan recovery.

## Target Berikutnya

Hot-path siswa sudah hybrid di Nginx: Go primary, FastAPI fallback. Target berikutnya adalah
**plane-aligned composition untuk sisa FastAPI**, bukan membalik enam rute ke Python dan bukan
microservices.

```text
SafeLine -> Nginx
  -> student hot-path Go (enam rute) + FastAPI backup
  -> student FastAPI composition (login, poll, non-hot-path)
  -> control FastAPI composition -> control capabilities

Kedua runtime
  -> PostgreSQL adapter -> PgBouncer -> PostgreSQL
  -> Redis adapter -> cache/lock/stream/coordination
  -> post-commit monitoring events
```

- Pertahankan kontrak HTTP yang ada. Klien tidak memilih runtime.
- Tambahan rute ke Go hanya setelah gerbang di bawah lulus. Enam rute closeout tidak diulang
  dari nol kecuali regresi.
- Satu repository, satu schema, PostgreSQL, dan Redis pada VPS saat ini.

## Gerbang Performa dan Go

Tidak ada runtime yang boleh diklaim lebih cepat berdasarkan jumlah worker, container sehat,
bahasa implementasi, atau unit test. Promosi rute Go tambahan harus melewati seluruh gerbang
berikut. Enam rute closeout sudah melewatinya pada 2026-08-28:

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
- Go hot-path: `go/cmd/server/main.go`
- Go worker opsional: `go/cmd/worker/main.go`
- Nginx canary live: `runtime_control/nginx.{start,join,answer,autosave,batch,submit}-canary.conf`
- Closeout probe: `scripts/go_hotpath_lifecycle.py`
- Android: `android-kiosk/app/src/main/java/id/siab1/kiosk/`
- Flutter: `flutter_client_code/lib/main.dart`
- Compose: `docker-compose.production.yml`
- Nginx: `docker/nginx.production.conf`
