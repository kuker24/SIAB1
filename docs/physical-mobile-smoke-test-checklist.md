# Physical APK Smoke Test Checklist

Checklist ini untuk panitia/operator yang memegang HP Android nyata. Agent tidak melakukan build/distribute APK baru. Gunakan **APK existing** yang sudah dipakai/ditargetkan untuk ujian.

## Aturan Utama

- [ ] Tidak build APK baru.
- [ ] Tidak install APK dari sumber tidak resmi.
- [ ] Tidak mengubah endpoint/base URL production saat ujian aktif.
- [ ] Tidak menggunakan akun siswa real jika tersedia akun synthetic/test yang aman.
- [ ] Tidak melakukan load test; hanya 1–3 HP Android nyata.

## Perangkat Uji

Uji minimal pada 1 HP, ideal 3 HP Android berbeda:

- [ ] HP 1: Android versi umum panitia/siswa.
- [ ] HP 2: ukuran layar kecil/sedang.
- [ ] HP 3: jaringan berbeda jika aman.

Catat:

```text
Tanggal/jam:
Nama penguji:
Versi APK jika terlihat:
Model HP:
Android version:
Jaringan:
Akun test:
Hasil akhir: PASS/FAIL
```

## 1. Launch dan Login Siswa

- [ ] APK terbuka tanpa crash.
- [ ] Halaman login tampil.
- [ ] Login siswa test berhasil.
- [ ] Pesan error login invalid tampil wajar jika kredensial salah.
- [ ] Tidak ada prompt permission aneh yang mengganggu ujian.

## 2. Join Token

- [ ] Input token ujian test.
- [ ] Join token berhasil.
- [ ] Informasi ujian tampil benar: nama ujian/mapel/durasi.
- [ ] Token invalid menampilkan pesan aman dan tidak crash.

## 3. Start Exam

- [ ] Start exam berhasil.
- [ ] Tidak ada loop loading panjang.
- [ ] Timer mulai sesuai durasi.
- [ ] Identitas/ujian yang tampil sesuai.

## 4. Timer dan Navigasi Soal

- [ ] Timer berjalan turun normal.
- [ ] Pindah soal berikut/sebelumnya berhasil.
- [ ] Nomor/status soal terlihat wajar.
- [ ] Rotasi layar/perubahan fokus tidak merusak timer jika policy mengizinkan.

## 5. Jawab Soal dan Autosave

- [ ] Pilih jawaban pada beberapa soal.
- [ ] Pindah soal lalu kembali: jawaban tetap ada.
- [ ] Indikator save/autosave/retry tidak error terus-menerus.
- [ ] Jika ada soal bergambar, preview/zoom bisa dibuka dan ditutup.
- [ ] Tidak ada jawaban hilang setelah navigasi normal.

## 6. Offline/Reconnect Ringan Jika Aman

Hanya lakukan jika disetujui panitia dan bukan pada ujian real aktif:

- [ ] Matikan jaringan 5–10 detik.
- [ ] Aplikasi menampilkan kondisi koneksi/retry secara wajar.
- [ ] Nyalakan jaringan kembali.
- [ ] Jawaban tetap ada di UI.
- [ ] Autosave pulih tanpa siswa keluar aplikasi.

Jika test ini berisiko mengganggu sesi real, lewati dan catat `SKIPPED`.

## 7. Final Submit

- [ ] Jawab beberapa soal.
- [ ] Tekan final submit sekali.
- [ ] Konfirmasi submit tampil wajar jika ada.
- [ ] Final submit berhasil.
- [ ] Aplikasi tidak kembali ke mode pengerjaan setelah submit.
- [ ] Tidak perlu menekan submit berkali-kali.

## 8. Result/Grading

- [ ] Result/grading tampil sesuai konfigurasi ujian.
- [ ] Jika hasil disembunyikan oleh policy, aplikasi menampilkan pesan wajar.
- [ ] Tidak ada data peserta lain terlihat.

## 9. Screenshot / Task Switch / Root / Tamper Detection

Sesuai policy APK/SXB yang berlaku:

- [ ] Screenshot diblokir atau dicatat sesuai konfigurasi.
- [ ] Task switch/background terdeteksi sesuai konfigurasi.
- [ ] Root/tamper detection tidak dilemahkan.
- [ ] Pelanggaran ringan muncul sebagai warning/log sesuai policy.
- [ ] Tidak ada false positive masif pada penggunaan normal.

## 10. Emergency Exit / Admin Command

- [ ] Emergency exit/admin command tetap tersedia untuk panitia sesuai prosedur.
- [ ] Fitur tidak tersedia bebas untuk siswa tanpa otorisasi.
- [ ] Penggunaan emergency dicatat oleh panitia.
- [ ] Jangan menghapus/menonaktifkan fitur emergency saat ujian aktif.

## 11. Cheating Detection di Admin Dashboard

- [ ] Trigger pelanggaran test yang aman.
- [ ] Admin dashboard summary/aggregate menunjukkan event cheating/violation.
- [ ] Dashboard tidak perlu detail refresh agresif.
- [ ] Jika endpoint violation sedang di-shed oleh Nginx emergency, catat status operasional dan jangan ubah saat ujian aktif tanpa approval.

## 12. PASS/FAIL Criteria

### PASS

- Login, join token, start exam, answer save, autosave, dan final submit berhasil.
- Timer stabil.
- APK/SXB security detection tidak melemah.
- Cheating detection terlihat di dashboard summary/aggregate bila jalur operasional aktif.
- Tidak perlu APK baru.

### FAIL / NO-GO

- APK crash pada login/start/answer/final-submit.
- Jawaban hilang setelah navigasi normal.
- Final submit gagal atau membutuhkan spam klik.
- Security validation APK/SXB tidak berjalan.
- Emergency exit/admin command tidak dapat digunakan panitia.
- Cheating detection hilang total tanpa status operational yang disetujui.

## 13. Laporan Hasil

```text
Overall: PASS/FAIL
Device count:
Login:
Join token:
Start exam:
Timer:
Answer save/autosave:
Image zoom if applicable:
Offline/reconnect: PASS/FAIL/SKIPPED
Final submit:
Result/grading:
Security detection:
Emergency/admin command:
Cheating dashboard:
Catatan risiko:
Rekomendasi GO/NO-GO:
```
