# Production Readiness Evidence - 2026-08-24

Dokumen ini mencatat pemeriksaan terkontrol terhadap deployment
`siab.man1rokanhulu.cloud`. Semua fixture load/monitoring bersifat sintetis dan telah dihapus.

## Recovery dan Operasional

- Backup database pra-perubahan dibuat di
  `/opt/siab1/backups/pre-readiness-20260824T201746.sql.gz` beserta SHA-256.
- Timer `siab1-backup.timer` aktif setiap hari pukul 01:30 WIB dengan retention 30 hari.
- Timer `siab1-restore-drill.timer` aktif mingguan. Drill pertama memvalidasi checksum,
  memulihkan backup ke database sementara, memeriksa tabel inti, dan selesai sukses.
- Host-controlled restart path aktif tanpa Docker socket di container.
- Auto-restart stateless dijadwalkan Minggu 00:30 WIB dengan buffer ujian 60 menit.
  PostgreSQL dan Redis tidak termasuk restart plan. Dry-run guard lulus dengan nol sesi,
  ujian berjalan, dan ujian dalam buffer.
- Capacity snapshot read-only selesai melalui `sudo` tanpa mengubah permission `.env`.

## Load Test Publik

Phased test `50 -> 200 -> 620` melewati SafeLine dan hostname publik. Seluruh fase memiliki
100% login, start, status, remaining-time, answer, dan final-submit success. Tidak ada stale
idle-in-transaction, rejected Redis connection, eviction, atau deadlock. Cleanup menyisakan
nol fixture sintetis dan health tetap sukses.

| Concurrent | Login p95 | Start p95 | Answer p95 | Submit p95 |
|---:|---:|---:|---:|---:|
| 50 | 3.80 s | 1.26 s | 1.36 s | 1.04 s |
| 200 | 15.36 s | 3.94 s | 4.91 s | 3.95 s |
| 620 | 24.19 s | 17.77 s | 14.03 s | 13.11 s |

Fase 620 berada di bawah gate sertifikasi repository untuk start (30 s), status (12 s),
remaining-time (12 s), answer (30 s), dan submit (20 s). Latency tetap perlu dipantau pada
gelombang nyata; hasil ini membuktikan correctness/capacity gate, bukan target pengalaman ideal.

## Smoke Fungsional

- Violation queue dan WebSocket monitoring: 11 event queued menghasilkan 11 broadcast dan
  11 aggregate monitoring; dua event warning-only berstatus `ignored` sesuai policy.
- Upload gambar melalui hostname publik: HTTP 200, file tersimpan, lalu fixture dihapus.
- Writable bind mount diperbaiki untuk UID aplikasi pada uploads, logs, SEB config, APK builds,
  dan generated static directories.
- Heavy export mengembalikan HTTP 503 sesuai konfigurasi produksi
  `EXAM_PEAK_MODE=true` dan `HEAVY_EXPORT_ENABLED=false`; success-path tidak diaktifkan saat
  peak mode.
- Flutter stable: dependency resolution, `flutter analyze`, dan widget test lulus.

## Remaining External Gates

- Android `2.0.2+4` belum dapat ditandatangani tanpa release keystore dan credentials.
- Physical-device smoke APK/SXB pada 1-3 perangkat nyata masih memerlukan operator/perangkat.
- Export success-path hanya boleh diuji pada maintenance mode dengan heavy export diaktifkan
  secara eksplisit; production peak-mode rejection sudah terverifikasi.
