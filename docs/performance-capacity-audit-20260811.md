# Audit Kapasitas SIAB1 — 2026-08-11

## Ringkasan keputusan

**Keputusan saat ini: NO-GO untuk klaim 1.000 siswa aktif bersamaan.**

Alasannya bukan tebakan:

1. Uji 100 VU masih baik secara fungsi.
2. Uji 300 VU sudah mempunyai latency simpan jawaban p95 sekitar **18,5 detik**.
3. Uji 600 VU mempunyai latency p95 sekitar **45,3 detik**, p99 sekitar **70,2 detik**, dan maksimum sekitar **164 detik**.
4. Insiden production pernah terjadi saat sekitar **262 sesi masih aktif**, dengan load 80,87, sekitar 346 koneksi database, sekitar 188 `idle in transaction`, dan 60–80+ request menunggu advisory lock.
5. Batas RAM container aktif di Compose berjumlah sekitar **18,25 GiB**, sedangkan VPS historis memiliki sekitar **15–16 GiB RAM**. Angka ini belum memasukkan RAM OS, Docker, page cache, TLS, dan lonjakan sementara.
6. Tidak ada hasil uji sukses untuk 1.000 siswa.

Sistem mempunyai kontrol integritas yang baik. Namun, kapasitas tulis database dan pengelolaan resource belum cukup untuk menyatakan 1.000 siswa aman.

## Batas audit

- Target: 1.000 siswa aktif bersamaan.
- VPS production hanya boleh dibaca.
- Tidak ada load test, restart, deploy, cleanup, atau perubahan data production.
- SSH ke `103.175.218.56:22` masih timeout pada 2026-08-11.
- Karena itu, kondisi RAM, disk, container, DB, Redis, dan konfigurasi aktif VPS sekarang berstatus **belum diketahui**.

## Cara membaca hasil

- **Terbukti:** ada bukti dari source, konfigurasi, atau hasil ukur.
- **Perkiraan:** hasil hitung dari konfigurasi, belum dibuktikan pada VPS sekarang.
- **Belum diketahui:** membutuhkan akses read-only ke VPS atau staging.

---

## 1. Arsitektur saat ini

### Komponen production

Dari `docker-compose.production.yml`:

- 8 container API siswa.
- Setiap API siswa memakai 2 worker Uvicorn.
- 2 container API admin/control, masing-masing 1 worker.
- Nginx sebagai reverse proxy dan load balancer.
- PostgreSQL 15.
- PgBouncer transaction pooling.
- Redis 7 dengan AOF.
- Satu Celery worker dengan `--pool=solo`.
- Celery Beat.
- Prometheus dan Grafana.

### Hal yang sudah baik

1. **Control-plane dipisahkan dari student-plane.**
   Traffic admin tidak selalu memakai worker siswa yang sama.

2. **PgBouncer dan `NullPool` sudah digunakan.**
   `app/database.py::_build_engine()` mencegah setiap worker membuat pool SQLAlchemy besar ketika melewati PgBouncer.

3. **Jalur jawaban menjaga integritas.**
   `AnswerSyncService.accept_single_answer()` memakai validasi, lock, upsert/idempotensi, commit, dan rollback yang jelas.

4. **Final submit bersifat idempotent.**
   Percobaan ulang pada sesi yang sudah submit mengembalikan hasil yang sudah ada.

5. **Cache validasi soal sudah ada.**
   Cache lokal mengurangi query soal/opsi yang berulang dan mempunyai TTL.

6. **Nginx mempunyai lane khusus.**
   Login, start, polling, answer, submit, monitor, dan admin mempunyai rate limit/routing terpisah.

7. **Redis dan DB pressure sudah mempunyai sebagian telemetry.**
   Sistem sudah punya runtime telemetry, Redis counters, dan health endpoints.

---

## 2. Masalah kapasitas utama

### P0 — Budget RAM tidak cocok dengan VPS historis

Batas RAM service aktif:

| Kelompok | Batas RAM |
|---|---:|
| 8 API siswa | 7.500 MiB |
| 2 API admin | 1.500 MiB |
| PostgreSQL | 5.632 MiB |
| Redis | 1.792 MiB |
| PgBouncer | 256 MiB |
| Nginx | 256 MiB |
| Celery worker + Beat | 768 MiB |
| Prometheus + Grafana | 768 MiB |
| **Total aktif** | **18.688 MiB / 18,25 GiB** |

Profile read replica menambah 400 MiB jika diaktifkan.

Batas container bukan berarti semua service selalu memakai maksimum. Namun, total batas yang lebih besar daripada RAM host membuat OOM, swap, dan resource contention mungkin terjadi saat puncak.

**Keputusan:** konfigurasi ini tidak boleh dianggap “right-sized for 16 GB” tanpa mengubah budget atau meningkatkan/memisahkan server.

### P0 — Pintu masuk API jauh lebih besar daripada kapasitas DB

Konfigurasi mempunyai:

- 16 worker siswa dengan `--limit-concurrency 220`.
- 2 worker admin dengan `--limit-concurrency 140`.
- PgBouncer backend maksimum 360.
- PostgreSQL `max_connections=420`.
- PgBouncer `QUERY_WAIT_TIMEOUT=90`.

Uvicorn menjelaskan bahwa `--limit-concurrency` menolak dengan HTTP 503 setelah batas worker tercapai. Idle keep-alive juga memakai budget. Dengan banyak worker, batas teoritis agregat dapat mendekati **3.800 koneksi/task**, sementara hanya ratusan transaksi DB dapat berjalan di belakang PgBouncer.

Ini memungkinkan terlalu banyak request menunggu DB/lock secara bersamaan. Timeout panjang juga menjaga antrean tetap hidup, lalu client melakukan retry dan menambah beban.

### P0 — Jalur simpan jawaban adalah bottleneck yang sudah terbukti

Bukti `docs/phase-4.3.2f-fresh-backup-production-live-validation-20260604.md`:

| Tier | Answer p95 | Answer p99 | DB active max | DB idle-tx max | Keputusan |
|---|---:|---:|---:|---:|---|
| 100 | 492 ms | 1,90 s | 12 | 16 | fungsi/data lulus |
| 300 | 18,50 s | 28,24 s | 38 | 57 | risiko performa |
| 600 | 45,34 s | 70,22 s | 143 | 138 | performance NO-GO |

Integritas data pada uji tersebut lulus. Masalahnya adalah latency dan tekanan DB.

Advisory lock tidak boleh dihapus sembarangan. Lock melindungi konsistensi jawaban. Yang harus dikurangi adalah jumlah write, duplicate payload, retry serentak, dan waktu transaksi.

### P0 — Insiden nyata terjadi jauh di bawah target 1.000

Bukti `docs/vps-capacity-review-20260602/02-incident-traffic-overload-20260602.md`:

- sekitar 262 sesi `in_progress`;
- load average 80,87 pada host 16 vCPU;
- PostgreSQL sekitar 221% CPU;
- API replica sekitar 130–190% CPU;
- sekitar 346 koneksi DB;
- sekitar 188 `idle in transaction`;
- 60–80+ advisory-lock waiters;
- sampel 90 detik: 4.958 HTTP 499 dan 686 HTTP 503.

Akar masalah yang tercatat adalah burst autosave/journal, lock queue, idle transaction, dan retry amplification.

### P1 — Satu Redis menangani terlalu banyak fungsi

Redis DB 0 dipakai untuk cache, runtime state, Pub/Sub, telemetry, lock, rate limiting, dan buffer. DB 1 dipakai Celery, tetapi batas memory dan eviction policy berlaku untuk seluruh Redis server.

Konfigurasi memakai:

- `maxmemory 1400mb`;
- `allkeys-lru`;
- AOF every second;
- container limit 1.792 MiB.

Jika memory penuh, key penting dan key biasa berada di bawah kebijakan eviction yang sama. Kondisi production sekarang belum dapat diperiksa.

### P1 — WebSocket membuat listener Redis per koneksi

`WebSocketManager.connect()` membuat satu task `_listen_redis()` dan satu Pub/Sub object untuk setiap WebSocket.

Pada 1.000 siswa, ini berarti sekitar 1.000 task listener dan subscription/socket state, tersebar di worker. Cleanup sudah ada saat disconnect, tetapi biaya RAM, Redis connection, dan fan-out belum pernah dibuktikan pada skala 1.000.

### P1 — Celery hanya punya satu slot eksekusi

Celery worker memakai `--pool=solo`. Beat menjadwalkan:

- answer queue setiap 5 detik;
- analytics refresh setiap 5 menit;
- close expired session setiap 30 detik;
- partition maintenance;
- disaster recovery drill.

Satu task berat dapat menahan task penting lain. Tugas kritis dan tugas maintenance belum dipisah ke queue/worker berbeda.

### P1 — Final submit dan export dapat memakai RAM besar

Final submit memuat pertanyaan, opsi, dan jawaban sebelum grading. Ini masuk akal untuk correctness, tetapi gelombang submit serentak perlu diukur.

Beberapa endpoint export/analytics/users memanggil `.all()` dan membuat PDF/DOCX/CSV di memory. Nginx juga masih merutekan PDF hasil ujian ke backend siswa. Fitur `HEAVY_EXPORT_ENABLED` default-nya `true` di Compose.

Saat ujian, export berat harus dinonaktifkan lewat profile production yang tervalidasi, bukan mengandalkan operator mengingatnya.

---

## 3. Efisiensi penyimpanan

### P0 — Tidak ada rotasi Docker log di Compose

Tidak ditemukan `logging.max-size` atau `logging.max-file` pada service production.

Jika Docker memakai default `json-file`, log dapat tumbuh tanpa batas. Kondisi log VPS sekarang belum diketahui karena SSH timeout.

### P0 — Docker build context sangat besar dan berbahaya

Tidak ada `.dockerignore`.

Dockerfile menjalankan `COPY . .`. Ukuran directory lokal sekitar **2,2 GB** dan mencakup:

- virtual environment;
- Flutter build;
- reports;
- APK builds;
- backup lokal;
- `.git`;
- file `.env*`;
- private key certificate di `docker/certs/`.

File tersebut memang diabaikan Git, tetapi **Git ignore bukan Docker ignore**. Tanpa `.dockerignore`, file dapat dikirim ke Docker daemon dan disalin ke image.

Dampak:

- build lambat;
- image membengkak;
- cache buruk;
- rahasia berisiko masuk layer image;
- transfer/deploy memakai storage lebih besar.

Ini update yang sangat mendesak.

### P0 — Path cron dan restore tidak konsisten

`install.sh` masih memasang cron dengan command di root seperti `./backup-comprehensive.sh`, tetapi script sekarang berada di `bin/`.

`bin/backup-comprehensive.sh` berpindah ke root repository. Sebaliknya, `bin/restore.sh` berpindah ke directory `bin/` lalu mencari `./recovery_sistem` di sana.

Artinya backup terjadwal dapat tidak jalan, dan restore dapat mencari lokasi yang salah. Restore juga bersifat destruktif dan tidak boleh dicoba di production untuk audit.

### P1 — Retensi belum lengkap

- Prometheus punya retensi 30 hari.
- Activity log melakukan auto-prune ketika endpoint admin tertentu dibuka, bukan melalui scheduler khusus.
- Partition maintenance sudah ada, tetapi hanya bekerja jika `exam_logs` benar-benar menjadi partitioned table.
- Upload, APK/SEB build, image cache, Redis AOF, Grafana, dan sejumlah data bisnis belum mempunyai quota/retensi yang terbukti berjalan.

### P1 — Backup belum bisa dianggap disaster recovery

Repository mempunyai script backup. Namun, audit belum membuktikan:

- cron aktif dan path benar;
- backup terbaru valid;
- checksum dan encryption;
- salinan offsite/immutable;
- restore sukses pada lingkungan terpisah.

Sampai bukti tersebut ada, backup adalah **belum terverifikasi**.

---

## 4. Monitoring

### Masalah utama

1. Prometheus hanya scrape `api:8000`, bukan semua 8 API siswa dan 2 API control.
2. Config menyebut postgres/redis/nginx/node exporter, tetapi service exporter tidak ada di Compose.
3. Endpoint `/metrics` secure-by-default dan membutuhkan bearer token atau explicit unauthenticated flag. Config Prometheus tidak mengirim authorization header.
4. Helper metric seperti `record_request()` tidak mempunyai caller yang ditemukan.
5. Health endpoint container tidak membuktikan latency, DB lock, PgBouncer wait, Redis eviction, atau disk pressure.

**Akibat:** container dapat berstatus healthy saat layanan sebenarnya sudah degraded. Hal ini juga tercatat pada insiden 2026-06-02.

---

## 5. Apakah aplikasi perlu di-update?

**Ya. Perlu update. Jangan langsung deploy. Update harus dilakukan bertahap dan dites.**

### P0 — Dependency yang punya kerentanan dikenal

`pip-audit -r requirements.txt` menemukan 58 advisory pada 6 package yang dideklarasikan:

| Package sekarang | Kandidat versi perbaikan minimum/aman dari audit |
|---|---|
| Starlette 0.52.1 | minimal 1.3.1 untuk menutup seluruh advisory yang ditampilkan |
| python-multipart 0.0.22 | minimal 0.0.31 |
| PyJWT 2.11.0 | minimal 2.13.0 |
| Pillow 12.1.1 | minimal 12.3.0 |
| pytest 9.0.2 | minimal 9.0.3 |
| cryptography 46.0.5 | upgrade terkontrol; audit menampilkan fix sampai 50.0.0 |

Versi terbaru yang terlihat pada 2026-08-11 antara lain FastAPI 0.141.1, Starlette 1.6.0, python-multipart 0.0.32, PyJWT 2.13.0, Pillow 12.3.0, dan cryptography 50.0.0.

Jangan mengubah semua sekaligus di production. Buat satu batch security update, lock versinya, jalankan test lengkap, lalu staging smoke/capacity regression.

### P0 — Security gate dapat memberi hasil lulus palsu

`scripts/check_security.py` mengembalikan sukses ketika `pip-audit` tidak tersedia atau timeout.

Pada audit ini, script mencetak “SECURITY CHECK PASSED” walaupun vulnerability scan dilewati. Ketika `pip-audit` dijalankan langsung terhadap `requirements.txt`, ditemukan kerentanan.

Release gate harus fail-closed untuk production: scanner hilang/timeout harus menggagalkan release, bukan meluluskan.

### P1 — Build tidak reproducible

Dependency berikut masih memakai range:

- pydantic;
- pydantic-settings;
- numpy;
- scipy;
- python-json-logger;
- reportlab;
- python-docx;
- openpyxl.

Dockerfile juga menginstal paket tambahan/range sebelum `requirements.txt`, termasuk pandas yang tidak dideklarasikan dan tidak ditemukan dipakai aplikasi.

Image `postgres:15-alpine`, `redis:7-alpine`, `nginx:alpine`, dan base Python tidak dipin ke digest.

### P1 — Tidak ada CI yang terlacak pada branch ini

Tidak ada file workflow di `.github/` yang terlacak pada branch saat audit. Karena itu, test, audit dependency, Compose validation, migration validation, dan image scan tidak dapat dianggap otomatis.

### P1 — Schema masih berubah saat setiap worker startup

Setiap worker menjalankan lifespan. Lifespan memanggil `init_db()`, yang menjalankan `Base.metadata.create_all()` dan compatibility ALTER/constraint checks.

Dengan 18 worker, startup/redeploy dapat menghasilkan banyak pemeriksaan DDL dan seed yang berjalan bersamaan. Schema production sebaiknya dikelola satu kali melalui migration job, bukan oleh semua API worker.

---

## 6. Hal yang belum dapat diverifikasi

Karena SSH timeout, audit belum mengetahui:

- RAM/swap sekarang;
- disk dan inode sekarang;
- effective Docker memory limits;
- apakah Compose `deploy.resources` benar-benar diterapkan runtime;
- container restart/OOM count;
- ukuran Docker logs, image cache, volume, PostgreSQL, WAL, Redis AOF, upload, dan backup;
- konfigurasi Nginx/PgBouncer/env yang benar-benar aktif;
- PgBouncer wait, DB lock, idle transaction, Redis eviction, dan WebSocket count sekarang;
- kondisi Prometheus target dan alert;
- cron/timer backup;
- backup offsite dan restore proof;
- vulnerability/image state di VPS.

Full test lokal juga belum dapat berjalan:

- `.venv-test` menunjuk path repository lama;
- `.venv` membutuhkan `libpython3.14.so.1.0` yang tidak ada;
- Python sistem tidak mempunyai pytest.

Ini blocker environment lokal, bukan bukti bahwa test aplikasi gagal.

---

## 7. Urutan perbaikan yang direkomendasikan

### P0 — sebelum ujian 1.000 siswa

1. Pulihkan akses read-only VPS dan ambil snapshot resource nyata.
2. Tambahkan `.dockerignore` yang menutup `.env*`, key/cert private, backup, reports, APK/build, Flutter build, virtualenv, `.git`, logs, dan artifact test.
3. Tambahkan rotasi Docker log dan alert disk/inode.
4. Perbaiki security update dan buat scanner fail-closed.
5. Perbaiki path cron backup/monitor dan desain restore yang konsisten.
6. Right-size total RAM terhadap host nyata, atau upgrade/pisahkan server.
7. Lengkapi metrics semua API, PgBouncer, PostgreSQL, Redis, Nginx, dan host.

### P1 — perbaikan bottleneck

1. Instrumentasikan waktu rate limit, validation, advisory lock, row lock, upsert, commit, Redis, dan publish.
2. Kurangi duplicate write: client debounce, coalesce/batch, satu in-flight write per session, event ID, backoff dengan jitter, dan deadline retry.
3. Jangan aktifkan queue/hybrid production sampai mekanisme 503 lama dipahami dan staging 600 lulus.
4. Review PgBouncer pool dengan data, bukan langsung mengganti angka production.
5. Pisahkan task Celery kritis dan maintenance.
6. Ubah WebSocket menjadi shared subscription/fan-out jika pengukuran 1.000 koneksi membuktikan listener-per-connection terlalu mahal.
7. Pindahkan export berat ke control/background worker dan paksa disabled saat peak mode.

### P2 — ketahanan jangka panjang

1. Migrasi schema terkelola; hentikan DDL pada startup API production.
2. Retensi terjadwal untuk logs, upload yatim, APK/SEB, backup, monitoring, dan artifact.
3. Backup encrypted/offsite dan restore drill berkala pada environment terpisah.
4. Pin dependency dan image digest.
5. Tambahkan CI blocking untuk test, security audit, migration, Compose, SBOM, dan image scan.
6. Pisahkan PostgreSQL dari app server untuk target besar; rekomendasi historis repository adalah minimal single-node 24 vCPU/32 GiB, dengan arsitektur terpisah lebih disarankan.

---

## 8. Syarat sertifikasi 1.000 siswa

Production tidak boleh digunakan sebagai tempat load test.

Buat staging disposable yang sama dengan target production. Jalankan berurutan:

1. 100 siswa;
2. 300 siswa;
3. 600 siswa;
4. 1.000 siswa.

Berhenti jika tier sebelumnya gagal.

Syarat lulus:

- nol jawaban hilang/rusak;
- nol finalisasi ganda;
- nol 5xx/timeout tak terduga pada answer/final submit;
- p95/p99 sesuai SLO yang ditetapkan sebelum tes;
- PgBouncer wait, lock, dan idle transaction tidak terus bertambah;
- Redis eviction/rejected/blocked = 0;
- tidak memakai swap dan tidak mendekati memory limit;
- disk/inode aman;
- semua telemetry tersedia;
- post-run integrity audit lulus;
- tier 1.000 lulus dua kali pada run terpisah.

Alat yang dapat digunakan kembali:

- `scripts/load_test_answer_sync.py` — staging, artifact `/tmp`;
- `scripts/prod_concurrent_exam_load.py` — staging disposable saja;
- `scripts/run_super_2000_certification.py` — staging disposable saja;
- `scripts/post_exam_audit_readonly.py` — audit integritas read-only.

---

## Keputusan akhir audit

| Area | Status |
|---|---|
| Integritas jalur jawaban | desain cukup kuat; uji lama lulus secara data |
| Efisiensi RAM | belum aman untuk host historis 16 GB |
| Efisiensi database | bottleneck terbukti pada 300–600 VU |
| Efisiensi Redis | belum terbukti pada 1.000; fungsi terlalu bercampur |
| Efisiensi storage | perlu update mendesak pada Docker context, log, backup, retensi |
| Monitoring | belum lengkap untuk keputusan kapasitas |
| Dependency/security | perlu update; release audit saat ini bisa fail-open |
| Kesiapan 1.000 siswa | **NO-GO / BELUM TERSERTIFIKASI** |

Langkah berikut yang paling aman adalah: pulihkan audit read-only VPS, perbaiki P0 secara lokal dan staging, lalu sertifikasi 100 → 300 → 600 → 1.000 pada staging terpisah.

---

## 9. Status remediasi lokal — 2026-08-11

Remediasi berikut sudah diterapkan **di working tree lokal**. Belum ada deploy, restart, perubahan environment, migration, cleanup, atau load test di VPS production.

### Selesai secara lokal

1. **Docker build context diamankan**
   - `.dockerignore` menutup `.env*`, private certificate/key, `.git`, virtualenv, report, backup, APK, Flutter build, dan artifact runtime.
   - File migration SQL dan `docker/init.sql` tetap tersedia untuk build.

2. **Docker log dibatasi**
   - Semua service production menggunakan `json-file` dengan `max-size=20m` dan `max-file=5`.

3. **Dependency rentan diperbarui**
   - Starlette, python-multipart, PyJWT, Pillow, pytest, dan cryptography diperbarui ke versi perbaikan.
   - `pip-audit` untuk dependency development dan runtime: tidak menemukan kerentanan dikenal.
   - Runtime production memakai `requirements.runtime.lock` dengan 71 package yang dipin tepat.

4. **Security release gate dibuat fail-closed**
   - Scanner hilang atau timeout sekarang menggagalkan gate.
   - Audit memeriksa `requirements.txt`, bukan hanya package yang kebetulan terpasang pada host.

5. **Backup/monitor/restore path diperbaiki**
   - Cron memakai path `bin/` dan quoted absolute project root.
   - Health monitor dan restore selalu berpindah ke repository root.
   - Restore berhenti sebelum tindakan destruktif jika safety backup gagal.
   - Health probe host memakai Nginx `http://127.0.0.1/health`.

6. **Observability API diperbaiki**
   - Prometheus scrape semua 8 API siswa dan 2 API control.
   - `/metrics` diblokir dari Nginx publik dan hanya diakses lewat Docker network.
   - Prometheus multiprocess mode menggabungkan dua worker per container.
   - Middleware mengisi metric request/latency dengan label endpoint yang dibatasi agar cardinality tidak membengkak.

7. **Safe peak defaults diterapkan**
   - Default Compose production: `EXAM_PEAK_MODE=true`.
   - Default Compose production: `HEAVY_EXPORT_ENABLED=false`.
   - Scheduled analytics materialized-view refresh dilewati saat peak mode aktif.

8. **Image production dirampingkan**
   - Multi-stage wheel build memisahkan compiler/header dari runtime.
   - pandas/Cython dan instalasi build berulang dihapus.
   - pytest dan pip-audit tidak masuk image production.
   - Image locked berhasil dibangun dengan ukuran sekitar 276 MiB.
   - Import aplikasi/runtime berhasil; file rahasia tidak ditemukan dalam image.

9. **CI blocking ditambahkan**
   - `.github/workflows/production-hardening.yml` menjalankan dependency audit, test hardening, backend test subset yang sehat, shell validation, Compose validation, dan build image.

10. **Tool read-only VPS ditambahkan**
    - `scripts/vps_capacity_snapshot_readonly.sh` mengumpulkan bukti aggregate host/Docker/PgBouncer/PostgreSQL/Redis/backup/timer.
    - `scripts/vps_capacity_preflight_readonly.py` memberi keputusan PASS/WARNING/CRITICAL/UNKNOWN tanpa mutasi.
    - UNKNOWN tidak dianggap aman.

### Bukti verifikasi lokal

- Focused hardening/preflight tests: 27 passed.
- Broad backend regression subset: 426 passed, 2 warning.
- Production image locked: build berhasil, sekitar 276 MiB.
- Runtime imports: berhasil.
- Runtime image: pytest/pip-audit/secrets tidak ada.
- Compose config: valid.
- Shell syntax dan ShellCheck error-level: valid.
- Workflow YAML: valid.
- Development dan runtime dependency audits: bersih.

Full suite masih memiliki kegagalan lama yang tidak disebabkan remediasi ini: template DOCX lokal hilang, bundle frontend tidak sinkron, dan source-guard lama masih mencari fungsi yang telah dipindahkan dari `app/api/exams.py`.

### Belum selesai karena membutuhkan akses/lingkungan lain

- SSH SIAB1 masih timeout saat banner exchange pada percobaan terakhir.
- Belum ada snapshot resource production terbaru.
- Belum ada deploy patch ini ke VPS.
- Belum ada migration atau perubahan resource budget production.
- Belum ada staging clone untuk sertifikasi 100 → 300 → 600 → 1.000.
- Karena itu status kapasitas tetap **NO-GO / BELUM TERSERTIFIKASI UNTUK 1.000**.

