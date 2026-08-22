# 03 - Capacity Upgrade and Reliability Recommendation

Tanggal: 2026-06-02

## Kesimpulan singkat

VPS saat ini masih mampu pulih setelah mitigasi, tetapi margin kapasitas untuk ujian besar masih tipis. Masalah utama bukan disk penuh, melainkan kombinasi:

- Burst traffic autosave/journal.
- PostgreSQL lock/connection pressure.
- API containers mendekati memory limit.
- Retry amplification saat backend lambat.
- Database, app, Redis, PgBouncer, monitoring masih berada di satu VPS.

Untuk ujian berikutnya dengan ratusan siswa bersamaan, disarankan upgrade kapasitas atau pisah database dari app server.

## Current capacity risk

### CPU

VPS punya 16 vCPU. Saat puncak:

```text
load average sempat >100
PostgreSQL CPU sempat >220%
API student replicas banyak >150% CPU
PgBouncer ±40% CPU
```

Load > jumlah vCPU berkali-kali menunjukkan antrean proses sangat tinggi.

### Memory

Total RAM sekitar 15 GiB. Saat puncak:

```text
API container limit 960 MiB per replica
Beberapa API mencapai 950-960 MiB
DB limit 5.5 GiB
Swap sempat terpakai ratusan MiB
```

Risiko:

- API container dekat limit bisa lambat/tertekan GC/memory pressure.
- Jika OOM terjadi, request siswa bisa terganggu.

### Database

PostgreSQL single container menerima semua beban:

```text
max_connections: 420
shared_buffers: 2560MB
work_mem: 4MB
PgBouncer transaction pooling
PgBouncer default_pool_size: 260
reserve_pool_size: 100
```

Risiko:

- Pool terlalu besar bisa membanjiri DB dengan terlalu banyak concurrency.
- Banyak concurrent write ke session/question memicu advisory lock queue.
- Idle-in-transaction dapat menahan resource sampai timeout.

### Network/API retry

Saat backend lambat:

```text
499 meningkat
502/503/504 meningkat
client retry/autosave retry bertambah
```

Retry dapat membuat traffic lebih besar daripada jumlah siswa asli.

## Rekomendasi upgrade VPS single-node

Jika ingin tetap satu VPS:

### Minimum aman untuk ujian besar berikutnya

```text
CPU: 24 vCPU
RAM: 32 GiB
Disk: 160 GiB NVMe
Swap: 4-8 GiB
```

Alasan:

- Memberi headroom untuk API + DB + Redis + monitoring.
- Mengurangi risiko API mendekati memory limit.
- DB bisa diberi RAM lebih besar.

### Lebih ideal single-node

```text
CPU: 32 vCPU
RAM: 64 GiB
Disk: 200-300 GiB NVMe
```

Alasan:

- Lebih aman untuk beberapa gelombang ujian dalam satu hari.
- Lebih banyak headroom saat retry burst.
- Monitoring/backup lokal tidak terlalu mengganggu.

## Rekomendasi arsitektur lebih baik: pisah database

Lebih disarankan daripada hanya memperbesar satu VPS:

### App server

```text
CPU: 16-24 vCPU
RAM: 24-32 GiB
Disk: 100-160 GiB NVMe
```

Menjalankan:

```text
Nginx
FastAPI replicas
Celery
Redis atau Redis tetap terpisah jika mampu
Prometheus/Grafana opsional
```

### Database server khusus

```text
CPU: 8-16 vCPU
RAM: 32-64 GiB
Disk: NVMe, minimal 160-300 GiB
```

Menjalankan:

```text
PostgreSQL
PgBouncer dekat DB atau di app server sesuai desain
```

Keuntungan:

- DB tidak berebut CPU/RAM dengan API.
- Lebih mudah tuning PostgreSQL.
- Lebih aman untuk backup/snapshot.
- Jika API retry burst, DB masih punya resource dedicated.

## Rekomendasi tuning sebelum/selain upgrade

### 1. Pertahankan idle transaction timeout rendah

Saat ujian besar:

```text
idle_in_transaction_session_timeout = 30s
```

Bahkan bisa dipertimbangkan:

```text
20s-30s
```

Tetapi harus diuji agar tidak memutus request valid yang butuh lama.

### 2. Review PgBouncer pool size

Current:

```text
default_pool_size = 260
reserve_pool_size = 100
max_client_conn = 5000
```

Rekomendasi review:

- Jangan biarkan app membuka terlalu banyak query paralel ke PostgreSQL.
- Pool yang lebih kecil bisa mengurangi DB thrashing walau menambah antrean di PgBouncer.
- Perlu load test untuk angka aman.

Candidate awal untuk diuji, bukan langsung produksi saat ujian:

```text
default_pool_size: 120-180
reserve_pool_size: 40-80
```

### 3. Jadikan violation logging asynchronous/non-critical

Saat ini emergency rule membuat:

```text
/api/exams/log-violation -> 204
```

Solusi permanen yang lebih baik:

- Endpoint menerima event cepat.
- Simpan ke Redis queue/list atau Celery queue.
- Worker menulis ke DB secara batch/rate-limited.
- Jika queue penuh, drop event non-critical dengan metrik.

Prioritas: jawaban siswa > final submit > session status > monitoring violation.

### 4. Kurangi frekuensi autosave/journal saat server busy

Client sebaiknya menghormati:

- `Retry-After` header.
- Exponential backoff.
- Jitter random.
- Jangan retry serentak tiap 1 detik.

Jika backend mengembalikan `429/503`, client perlu menunggu lebih lama, misalnya 5-15 detik.

### 5. Coalesce answer writes per session

Masalah utama terlihat pada write paralel per session/question. Solusi permanen:

- Simpan perubahan jawaban lokal client.
- Kirim batch lebih jarang.
- Server menulis latest answer per question.
- Hindari mengirim ulang payload yang sama.
- Gunakan Redis buffer/journal lalu DB batch flush.

### 6. Pisahkan endpoint final submit dari autosave pressure

Final submit harus punya jalur prioritas:

- Nginx location khusus sudah ada.
- Perlu pastikan server-side final submit tidak terjebak di antrean lock panjang dari autosave.
- Bisa pertimbangkan draining/short timeout untuk autosave saat session final submit.

### 7. Monitoring admin jangan polling berat saat ujian

Sudah ada patch low-risk polling guard. Lanjutkan:

- Hidden-tab pause.
- In-flight guard.
- Debounce.
- Cache live stats.
- Batasi monitoring detail/pelanggaran saat puncak.

## Runbook sebelum ujian besar berikutnya

### T-60 menit

1. Cek container health.
2. Cek disk free.
3. Cek DB activity harus rendah.
4. Cek Redis memory.
5. Cek emergency rule apakah sengaja aktif/nonaktif.
6. Cek jadwal ujian dan jumlah peserta.

### T-15 menit

1. Buka `/health`.
2. Buka `/student/dashboard.html`.
3. Buka admin dashboard/monitoring secukupnya.
4. Pastikan stale idle transaction = 0.

### Saat ujian

Monitor tiap 2-5 menit:

```text
uptime
Docker stats DB/API/PgBouncer
pg_stat_activity counts
nginx endpoint counts
status code 499/502/503
```

Jika overload:

1. Jangan restart container dulu.
2. Terminate stale idle transaction >30s.
3. Pastikan log-violation shed aktif jika kondisi darurat.
4. Jika tetap berat, pertimbangkan rate-limit/temporary shed endpoint non-critical lain, bukan final submit.

### Setelah ujian selesai

1. Pastikan mayoritas session `submitted`.
2. Rollback emergency Nginx rule jika tidak diperlukan.
3. Review logs dan DB metrics.
4. Buat patch permanen untuk queue/backoff/tuning.

## Keputusan yang perlu dibuat pemilik sistem

1. Apakah tetap single VPS atau pisah DB?
2. Berapa target concurrent siswa realistis?
3. Apakah violation log boleh bersifat best-effort saat overload?
4. Apakah autosave boleh ditunda/backoff lebih agresif saat server sibuk?
5. Apakah perlu load test sebelum ujian besar berikutnya?

## Rekomendasi prioritas

### Prioritas 0 - Hari ujian aktif

- Jangan rollback emergency shed sebelum semua ujian selesai.
- Jangan restart DB/API kecuali benar-benar crash.
- Monitor dan cleanup stale transaction bila perlu.

### Prioritas 1 - Setelah ujian hari ini

- Buat solusi permanen untuk violation logging asynchronous.
- Tambahkan client backoff untuk autosave/journal.
- Review PgBouncer pool size.
- Load test dengan skenario 300-600 siswa.

### Prioritas 2 - Infrastruktur

- Upgrade ke 24 vCPU/32 GiB RAM minimal jika tetap single VPS.
- Lebih baik pisah DB ke server khusus 8-16 vCPU/32-64 GiB RAM.
- Tambah disk NVMe minimal 160 GiB.
