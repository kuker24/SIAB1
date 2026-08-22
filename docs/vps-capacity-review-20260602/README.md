# VPS Capacity Review - Ujian Online

Tanggal dibuat: 2026-06-02

Folder ini berisi dokumentasi khusus VPS production, insiden overload saat ujian, mitigasi darurat yang sedang aktif, dan bahan pertimbangan upgrade/pindah VPS.

## Tujuan

1. Menyimpan spesifikasi VPS dan arsitektur runtime production secara aman.
2. Mendokumentasikan masalah traffic tinggi yang terjadi pada 2026-06-02.
3. Menyediakan rekomendasi kapasitas untuk ujian berikutnya.
4. Menyediakan prompt khusus agar AI reviewer di GitHub/ChatGPT Connector dapat memberi rekomendasi.

## Batas keamanan dokumen

Dokumen ini sengaja **tidak** mencantumkan:

- Password database.
- Secret key/JWT key.
- Token Telegram.
- Private SSH key.
- Isi `.env` production.
- Data pribadi siswa.
- Jawaban/hasil ujian siswa.

Yang dicantumkan hanya informasi operasional/capacity yang dibutuhkan untuk review.

## File

- [`01-vps-specification.md`](01-vps-specification.md) - spesifikasi VPS dan layanan production.
- [`02-incident-traffic-overload-20260602.md`](02-incident-traffic-overload-20260602.md) - kronologi masalah traffic tinggi dan mitigasi.
- [`03-capacity-upgrade-recommendation.md`](03-capacity-upgrade-recommendation.md) - opsi upgrade/pindah VPS dan prioritas perbaikan.
- [`04-ai-review-prompt.md`](04-ai-review-prompt.md) - prompt untuk AI code/capacity review di GitHub.

## Status ringkas terakhir

Snapshot terakhir yang tercatat pada 2026-06-02 09:45 WIB:

- VPS kembali responsif setelah overload pagi.
- Sesi `in_progress` kembali naik karena gelombang ujian 09:30 sedang berjalan.
- Emergency traffic shed untuk `/api/exams/log-violation` masih aktif sementara.
- DB idle transaction timeout untuk user aplikasi aktif `30s`.

Mitigasi darurat sebaiknya dipertahankan sampai ujian hari ini selesai, lalu dievaluasi/rollback terkontrol.
