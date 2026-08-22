# 01 - VPS Production Specification

Tanggal snapshot: 2026-06-02 09:45 WIB

## Identitas production

- Hostname: `adminujian`
- Domain publik: `man1rokanhulu.cloud`
- Public IP: `103.175.218.56`
- Path aplikasi di VPS: `/root/ujian_online`
- Runtime utama: Docker Compose production
- Compose file: `docker-compose.production.yml`
- Nginx config host: `/root/ujian_online/docker/nginx.production.conf`

> Catatan keamanan: detail akses SSH, private key, password, token, dan file `.env` tidak dicantumkan.

## Sistem operasi

- OS: Ubuntu 22.04.5 LTS (Jammy Jellyfish)
- Kernel: Linux 5.15.0-177-generic x86_64
- Docker: Docker 29.3.0
- Docker Compose: v5.1.0

## CPU

- vCPU: 16
- Architecture: x86_64
- Model: Common KVM processor
- Socket: 1
- Core per socket: 16
- Thread per core: 1
- Virtualization: full

## Memory dan swap

Snapshot 2026-06-02 09:45 WIB:

```text
Mem total: 15 GiB
Mem used: 10 GiB
Mem free: 2.8 GiB
Mem available: 4.8 GiB
Swap total: 2.0 GiB
Swap used: 410 MiB
```

Observasi:

- Saat overload pagi, memory masih tidak habis total, tetapi beberapa API container mendekati limit `960 MiB`.
- Swap sempat terpakai ratusan MiB, menandakan pressure cukup tinggi.
- Bottleneck utama lebih terlihat pada DB lock/connection/CPU daripada disk penuh.

## Disk

Snapshot:

```text
Root disk: /dev/sda1
Size: 58 GiB
Used: 26 GiB
Available: 33 GiB
Use: 44%
```

Layout ringkas:

```text
sda: 60G disk
sda1: 59.9G mounted at /
```

Observasi:

- Disk belum penuh.
- Untuk growth produksi dan backup lokal, kapasitas 60G mulai terbatas.
- Disarankan minimal 120G-160G NVMe jika tetap single VPS.

## Layanan Docker production

Layanan aktif:

```text
grafana
prometheus
ujian_online-nginx-1
ujian_online-api-1
ujian_online-api2-1
ujian_online-api3-1
ujian_online-api4-1
ujian_online-api5-1
ujian_online-api6-1
ujian_online-api7-1
ujian_online-api8-1
ujian_online-api_admin-1
ujian_online-api_admin2-1
ujian_online-db-1
ujian_online-pgbouncer-1
ujian_online-redis-1
ujian_online-celery_worker-1
ujian_online-celery_beat-1
```

Status terakhir semua container utama: `healthy`.

## Alur arsitektur runtime

Ringkas:

```text
Client siswa/admin
  -> Cloudflare/domain
  -> Nginx container
  -> FastAPI student replicas api1-api8
  -> FastAPI control/admin replicas api_admin/api_admin2
  -> PgBouncer
  -> PostgreSQL container
  -> Redis container
```

Komponen async/background:

```text
Celery worker
Celery beat
Redis broker/cache/session runtime
```

Monitoring:

```text
Prometheus
Grafana
```

## Resource limit container yang terlihat dari runtime

Snapshot `docker stats` menunjukkan limit penting:

```text
nginx: 256 MiB
api1-api8: 960 MiB per container
api_admin/api_admin2: 768 MiB per container
db/PostgreSQL: 5.5 GiB
redis: 1.75 GiB
pgbouncer: 256 MiB
celery_worker: 512 MiB
celery_beat: 128 MiB
prometheus: 512 MiB
grafana: 256 MiB
```

Observasi:

- Saat traffic tinggi, beberapa container API mencapai sekitar `950-960 MiB`, mendekati limit.
- PostgreSQL pernah mencapai CPU >200% saat overload.
- PgBouncer pernah CPU sekitar 40% saat antrean request DB tinggi.

## PostgreSQL/PgBouncer setting penting

Snapshot:

```text
PostgreSQL max_connections: 420
idle_in_transaction_session_timeout: 30s
shared_buffers: 2560MB
work_mem: 4MB
PgBouncer pool_mode: transaction
PgBouncer max_client_conn: 5000
PgBouncer default_pool_size: 260
PgBouncer reserve_pool_size: 100
```

Catatan:

- `idle_in_transaction_session_timeout = 30s` adalah mitigasi darurat/operasional yang aktif setelah insiden overload.
- Sebelumnya effective timeout command-line PostgreSQL adalah `45s`; lalu diturunkan pada level role/database `examuser` menjadi `30s`.
- `default_pool_size 260` + `reserve_pool_size 100` berpotensi terlalu agresif untuk PostgreSQL single-node dengan max connection 420 saat semua API replica sibuk.

## Snapshot normal setelah pemulihan

2026-06-02 08:57 WIB:

```text
load average: 2.21, 6.29, 18.81
PostgreSQL CPU: ±5.7%
PgBouncer CPU: ±1.8%
stale idle transaction: 0
/health: 200 0.011s
/admin/dashboard.html: 200 0.013s
/admin/monitoring.html: 200 0.010s
/student/dashboard.html: 200 0.026s
```

2026-06-02 09:45 WIB saat gelombang berikutnya berjalan:

```text
submitted: 4356
in_progress: 131
PostgreSQL activity: mostly idle, only 2 idle-in-transaction seen in snapshot
Emergency log-violation shed: active
```
