# Rekap Aman Bahasa Inggris — Ujian Utama vs Ujian Ke II (2026-06-03)

Dokumen ini dibuat sebagai laporan operasional aman berdasarkan pemeriksaan **read-only** pada VPS produksi. Tidak ada perubahan database, nilai, sesi, jawaban, soal, publish status, atau konfigurasi layanan.

## Tujuan

Menjawab pertanyaan operasional: apakah rendahnya jumlah peserta pada empat exam “Ujian Ke II” disebabkan siswa tidak ikut atau ada bug, dan bagaimana rekap nilai sebaiknya diperlakukan.

## Ringkasan Kesimpulan

1. Data session tidak hilang dan tidak terlihat sebagai bug massal.
2. Mayoritas siswa Bahasa Inggris kelas X dan XI sudah mengerjakan **ujian utama**.
3. Empat exam “Ujian Ke II” hanya diakses oleh 1–2 siswa per kelas.
4. Paket soal Ujian Ke II **sama antar kelas paralel pada tingkat yang sama**, tetapi **tidak sama penuh** dengan ujian utama.
5. Karena paket soal berbeda, nilai Ujian Ke II sebaiknya diperlakukan sebagai **susulan/ujian kedua terpisah**, bukan digabung otomatis sebagai satu paket identik dengan ujian utama.

## Exam Acuan Rekap

| Tingkat | Exam utama untuk rekap normal | Exam Ujian Ke II/susulan |
|---|---|---|
| X | ID 547 — `ASA BAHASA INGGRIS X` | ID 575 — X A; ID 577 — X D |
| XI | ID 546 — `ASA Bahasa Inggris XI` | ID 576 — XI D; ID 578 — XI C |

## Partisipasi Ujian Ke II

| Exam Ke II | Kelas | Target siswa aktif | Mulai Ujian Ke II | Tidak mulai Ujian Ke II | Dari yang tidak mulai, sudah ikut ujian utama |
|---:|---|---:|---:|---:|---:|
| 575 | X A | 32 | 1 | 31 | 31 |
| 576 | XI D | 26 | 2 | 24 | 24 |
| 577 | X D | 31 | 1 | 30 | 29 |
| 578 | XI C | 28 | 1 | 27 | 26 |

Catatan:
- X D memiliki 1 siswa aktif yang tidak punya session Bahasa Inggris hari itu pada exam utama maupun Ujian Ke II.
- XI C memiliki 1 siswa aktif yang tidak punya session Bahasa Inggris hari itu pada exam utama maupun Ujian Ke II.
- Dari pemeriksaan agregat, keduanya tidak tampak sebagai kegagalan session massal.

## Status Session Ujian Ke II

Semua session yang tercatat pada exam Ujian Ke II memiliki alur normal:

- `SESSION_START`
- `EXAM_SUBMITTED`
- `SCORE_BREAKDOWN`

Tidak ditemukan indikasi agregat berupa gagal submit massal atau session hilang pada empat exam Ke II tersebut.

## Perbandingan Konten Soal

Pemeriksaan dilakukan memakai hash konten soal/opsi/kunci tanpa menampilkan teks soal, opsi, jawaban siswa, atau kunci jawaban.

| Perbandingan | Jumlah soal masing-masing | Soal sama persis | Kesimpulan |
|---|---:|---:|---|
| Ujian utama X ID 547 vs Ke II X ID 575/577 | 40 vs 40 | 10 | Tidak sama penuh |
| Ujian utama XI ID 546 vs Ke II XI ID 576/578 | 40 vs 40 | 16 | Tidak sama penuh |
| Ke II X A ID 575 vs Ke II X D ID 577 | 40 vs 40 | 40 | Sama penuh |
| Ke II XI D ID 576 vs Ke II XI C ID 578 | 40 vs 40 | 40 | Sama penuh |
| Ke II X vs Ke II XI | 40 vs 40 | 0 | Berbeda tingkat/paket |

## Rekomendasi Operasional Rekap

### 1. Rekap normal kelas X dan XI

Gunakan exam utama sebagai sumber rekap normal:

- Kelas X: exam ID 547
- Kelas XI: exam ID 546

Alasan: mayoritas peserta sudah mengerjakan dan submit pada exam utama.

### 2. Perlakuan Ujian Ke II

Perlakukan exam ID 575–578 sebagai **Ujian Ke II/susulan/remedial terpisah**.

Jangan gabungkan otomatis nilai Ujian Ke II ke daftar nilai utama tanpa label, karena paket soal tidak sama 100% dengan exam utama.

### 3. Jika siswa punya dua nilai

Jika seorang siswa memiliki nilai di ujian utama dan Ujian Ke II, pemilihan nilai akhir perlu kebijakan guru/madrasah, misalnya:

- pakai nilai ujian utama,
- pakai nilai Ujian Ke II,
- pakai nilai tertinggi,
- atau pakai nilai yang disahkan guru.

Keputusan ini sebaiknya dicatat manual di rekap agar tidak dianggap sebagai perubahan teknis otomatis oleh sistem.

### 4. Tindakan yang tidak dilakukan

Laporan ini tidak melakukan:

- perubahan nilai,
- penghapusan session,
- pemindahan jawaban antar exam,
- penggabungan nilai otomatis,
- perubahan publish status,
- perubahan soal/opsi/kunci,
- restart/deploy layanan.

## Status Akhir

Aman untuk memakai exam utama sebagai rekap utama dan menyimpan Ujian Ke II sebagai catatan susulan/ujian kedua terpisah.
