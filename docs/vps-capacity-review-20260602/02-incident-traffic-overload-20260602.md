# 02 - Incident Report: Traffic Overload 2026-06-02

Tanggal insiden: 2026-06-02 pagi WIB

## Ringkasan

Saat ujian pagi berlangsung, dashboard admin/guru/pengawas sempat sulit/tidak bisa diakses. Pemeriksaan VPS menunjukkan siswa yang sedang ujian tidak putus total, tetapi sistem berada dalam kondisi degraded karena API/DB overload.

Patch admin polling yang sebelumnya dideploy bukan penyebab utama. Traffic terberat berasal dari endpoint runtime siswa, terutama autosave/journal/violation logging.

## Dampak yang terlihat

- Dashboard admin/guru/pengawas tidak responsif atau timeout.
- Beberapa endpoint siswa lambat/timeout.
- Banyak request `499`, `502`, `503`, dan sebagian `504`.
- Autosave dan status polling mengalami retry/timeout.
- Final submit tetap dijaga sebagai prioritas; tidak diblokir.

## Kondisi awal saat dicek

Sekitar 08:14 WIB:

```text
load average: 80.87, 64.00, 33.19
Mem total: 15 GiB
Mem available: 3.2 GiB
Disk /: 42% used
```

Container masih `healthy`, tetapi resource tinggi:

```text
PostgreSQL CPU: ±221%
PgBouncer CPU: ±40%
API student replicas: banyak di 130%-190% CPU
Nginx CPU: ±30%
```

Endpoint check:

```text
/health: sempat cepat, lalu beberapa kali timeout saat puncak
/admin/dashboard.html: kadang cepat karena static/control lane
/teacher/dashboard.html: timeout
/student/dashboard.html: sempat cepat lalu timeout saat DB penuh
```

## Traffic hot path saat puncak

Contoh hitungan 90 detik:

```text
1116 POST /api/student/exams/auto-save-batch
680  POST /api/exams/answer-journal/sync
675  POST /api/exams/log-violation
354  POST /api/exams/auto-save-batch
```

Status code contoh 90 detik:

```text
499: 4958
503: 686
200: 388
502: 48
504: 2
```

Interpretasi:

- `499`: client/proxy menutup koneksi sebelum response selesai, biasanya karena timeout/retry/refresh.
- `503/502/504`: upstream FastAPI/DB sedang terlalu lambat/penuh.
- Banyak retry memperparah beban.

## PostgreSQL pressure

Contoh kondisi DB saat puncak:

```text
pg_stat_activity total: sekitar 346 koneksi
idle in transaction: sekitar 188
active waiting advisory lock: 60-80+
active ClientRead: 60-90+
```

Query yang banyak terlihat:

```text
SELECT pg_advisory_xact_lock($1, $2)
SELECT pg_advisory_xact_lock(:namespace, :session_id)
```

Artinya banyak request menunggu lock per session/question. Ini masuk akal karena sistem mencoba serialisasi write jawaban agar aman, tetapi pada traffic tinggi antrean lock bertambah besar.

## Sesi aktif saat puncak

Sekitar 08:20 WIB:

```text
in_progress: ±262 siswa
submitted: ±4088 siswa
```

Saat 08:57 WIB setelah mayoritas submit:

```text
submitted: 4315
in_progress: 41
```

Saat 09:45 WIB gelombang berikutnya berjalan:

```text
submitted: 4356
in_progress: 131
```

## Mitigasi yang dilakukan

### 1. Read-only diagnosis

Dilakukan pengecekan aman tanpa restart:

- `docker compose ps`
- `docker stats --no-stream`
- `pg_stat_activity`
- `curl` local endpoint timing
- `docker logs nginx` untuk endpoint count/status code

### 2. Terminate stale idle transaction manual

Dilakukan beberapa kali:

```text
terminate idle in transaction >45s: 85 koneksi
terminate idle in transaction >30s: 48 koneksi
terminate idle in transaction >30s: 56 koneksi
terminate idle in transaction >30s: 36 koneksi
cleanup loop 5 menit: ratusan koneksi stale diterminasi bertahap
```

Risiko:

- Request autosave yang sedang nyangkut bisa gagal sekali.
- Client akan retry.
- Data yang sudah commit tidak dihapus.

Manfaat:

- Mengurangi transaksi menggantung yang menahan koneksi/lock.
- Membantu DB kembali responsif.

### 3. Set DB idle transaction timeout 30s

Ditemukan `ALTER SYSTEM` kalah oleh setting command-line PostgreSQL `45s`. Solusi yang efektif:

```sql
ALTER ROLE examuser SET idle_in_transaction_session_timeout = '30s';
ALTER DATABASE exam_system SET idle_in_transaction_session_timeout = '30s';
```

Verifikasi:

```text
show idle_in_transaction_session_timeout -> 30s
source -> user
```

### 4. Emergency shed endpoint log pelanggaran

Endpoint non-kritis untuk penyimpanan jawaban ditahan sementara di Nginx:

```text
/api/exams/log-violation -> 204 No Content
```

Marker config:

```text
EMERGENCY_TRAFFIC_SHED_LOG_VIOLATION_20260602
```

Backup config:

```text
/root/ujian_online/backups/emergency_disable_violation_log_20260602_083114/docker/nginx.production.conf
```

Alasan:

- Log pelanggaran menulis DB dan broadcast event.
- Saat overload, jawaban/autosave/final submit lebih penting.
- Mengurangi beban write non-essential.

Risiko:

- Log pelanggaran sementara tidak tercatat selama emergency rule aktif.
- Monitoring pelanggaran real-time menjadi tidak akurat selama periode ini.

### 5. Tidak dilakukan restart container

Selama mitigasi:

- Tidak restart API/DB.
- Tidak reboot VPS.
- Tidak menjalankan prune berbahaya.
- Tidak mematikan autosave/final submit.

## Kondisi setelah mitigasi

Sekitar 08:57 WIB:

```text
load average: 2.21, 6.29, 18.81
stale idle transaction: 0
PostgreSQL CPU: ±5.7%
PgBouncer CPU: ±1.8%
/health: 200 0.011s
/admin/dashboard.html: 200 0.013s
/admin/monitoring.html: 200 0.010s
/student/dashboard.html: 200 0.026s
```

Status code 60 detik setelah pulih:

```text
200: 288
101: 6
423: 3
403: 2
499: 1
```

## Root cause sementara

Root cause paling mungkin:

1. Traffic autosave/journal siswa melonjak bersamaan.
2. Banyak request menulis jawaban dan/atau sync journal secara paralel.
3. Per-session advisory lock melindungi konsistensi, tetapi menimbulkan antrean besar saat retry burst.
4. Banyak koneksi masuk status `idle in transaction` saat client timeout atau request menggantung.
5. Log violation ikut menambah write DB dan broadcast load, padahal bukan prioritas utama saat overload.
6. Retry amplification dari client/proxy memperbesar jumlah request saat backend lambat.

## Hal yang bukan penyebab utama

- Patch admin dashboard polling bukan penyebab utama karena endpoint terberat adalah runtime siswa.
- Disk tidak penuh.
- Container tidak crash total.
- Nginx/API/DB masih healthy secara container healthcheck, tetapi degraded secara latency/load.

## Status mitigasi saat dokumen dibuat

Masih aktif:

```text
idle_in_transaction_session_timeout = 30s
/api/exams/log-violation -> 204 No Content
```

Rekomendasi: pertahankan sampai seluruh ujian hari ini selesai, lalu rollback/ubah ke solusi permanen.
