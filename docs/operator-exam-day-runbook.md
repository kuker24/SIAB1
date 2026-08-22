# Operator Exam-Day Runbook

Runbook ini untuk panitia/operator saat ujian aktif pada mode mobile-first safe-mode direct. Tujuannya menjaga answer dan final-submit path tetap aman.

## Baseline Wajib

```text
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
EXAM_PEAK_MODE=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
APK_BUILD_ENDPOINT_ENABLED=false
HEAVY_EXPORT_ENABLED=false
```

Jangan mengubah baseline ini saat ujian aktif.

## 1. Sebelum Ujian

- [ ] Pastikan jadwal/token ujian benar.
- [ ] Pastikan APK existing sudah smoke test di 1–3 HP Android nyata.
- [ ] Pastikan panitia memahami wave plan 150–200 peserta.
- [ ] Pastikan admin dashboard hanya summary.
- [ ] Pastikan tidak ada agenda deploy/restart/load-test/build APK saat ujian.
- [ ] Pastikan jalur komunikasi escalation aktif.
- [ ] Siapkan daftar kontak operator, panitia ruang, dan decision owner.

## 2. Saat Login Gelombang

- Instruksikan peserta login bertahap 150–200 orang per gelombang.
- Tunggu stabil 2–5 menit sebelum gelombang berikutnya.
- Jangan semua kelas login/start bersamaan.
- Jika login timeout meningkat, tahan gelombang berikutnya dan eskalasi.

Read-only yang boleh dipantau:

- Error rate login/start/answer/final-submit.
- Status API/DB/Redis secara read-only.
- Dashboard summary.

## 3. Saat Start Exam

- Start exam juga bertahap per ruang/kelas.
- Jangan instruksikan semua peserta klik start di detik yang sama.
- Jika start exam lambat, minta peserta tunggu respons aplikasi.
- Jangan refresh/spam tombol start.

## 4. Saat Ujian Berlangsung

- Prioritaskan stabilitas answer autosave.
- Admin hanya membuka dashboard summary/aggregate.
- Jangan export PDF/Excel/report berat.
- Jangan membuka detail banyak siswa secara bersamaan.
- Cheating detection tetap dipantau dari aggregate dashboard.
- Catat anomali: waktu, ruang, jumlah siswa, gejala, endpoint/fitur terdampak.

## 5. Saat Final Submit

- Final submit dilakukan bertahap saat peserta selesai.
- Jangan meminta semua peserta menunggu sampai detik terakhir.
- Jika final submit lambat, minta peserta menunggu dan jangan spam submit.
- Hindari dashboard detail dan export saat final-submit peak.
- Final submit lebih penting daripada dashboard/report.

## 6. Jika Siswa Gagal Login

Langkah panitia:

1. Cek koneksi HP/sinyal Wi-Fi siswa.
2. Pastikan username/password benar.
3. Minta siswa tunggu 15–30 detik sebelum mencoba lagi.
4. Jangan membuat banyak percobaan paralel di banyak perangkat.
5. Jika beberapa siswa satu ruang gagal bersamaan, tahan login gelombang berikutnya dan eskalasi.

Catatan escalation:

- Waktu kejadian.
- Ruang/kelas.
- Jumlah siswa terdampak.
- Pesan error yang terlihat.
- Apakah siswa lain masih bisa login.

## 7. Jika Autosave Retry

- Minta siswa tetap di halaman ujian.
- Jangan langsung keluar aplikasi.
- Jangan spam pindah halaman/tombol jika indikator retry muncul.
- Jika koneksi kembali, pastikan jawaban terakhir masih terlihat.
- Jika banyak siswa retry bersamaan, kurangi aktivitas dashboard/detail dan eskalasi.

## 8. Jika Final Submit Lambat

- Jangan refresh aplikasi.
- Jangan menekan submit berulang-ulang.
- Tunggu respons aplikasi.
- Panitia mencatat siswa terdampak dan waktu submit.
- Operator memprioritaskan pengecekan final-submit error/timeout secara read-only.
- Jangan menjalankan export/report sampai final-submit peak selesai.

## 9. Jika Dashboard Lambat

- Kurangi jumlah admin yang membuka dashboard.
- Tutup tab dashboard detail yang tidak perlu.
- Gunakan summary/aggregate saja.
- Jangan refresh agresif.
- Jika answer/final-submit normal, jangan lakukan restart/deploy hanya karena dashboard lambat.

## 10. Jika Banyak 5xx

- Tahan gelombang login/start/submit berikutnya.
- Jangan deploy/restart tanpa approval explicit emergency.
- Catat endpoint/fitur terdampak jika terlihat: login, start, submit-answer, final-submit, dashboard.
- Cek apakah masalah hanya dashboard atau juga answer/final-submit.
- Eskalasi ke backend/DevOps reviewer dan decision owner.

## 11. Jika Redis/DB/API Pressure

Tindakan aman:

- Tahan wave berikutnya.
- Kurangi dashboard/admin detail.
- Stop export/report.
- Instruksikan final submit bertahap.
- Pantau read-only metrics/logs.

Tindakan yang tidak boleh dilakukan tanpa approval emergency:

- Restart DB/Redis/API/Nginx.
- Recreate container.
- Mengaktifkan hybrid/queue/runtime buffer.
- Migration production.
- Load test production.

## 12. Hal yang Tidak Boleh Dilakukan Panitia

- Jangan meminta semua peserta login/start/final-submit bersamaan.
- Jangan spam refresh dashboard.
- Jangan export/report berat saat ujian.
- Jangan install APK baru mendadak.
- Jangan membagikan token/password/log berisi data siswa ke luar kanal resmi.
- Jangan meminta operator deploy/restart kecuali emergency dan disetujui decision owner.

## 13. Escalation Template

Gunakan format ini saat melapor:

```text
Waktu:
Ruang/kelas:
Jumlah peserta terdampak:
Fitur terdampak: login/start/autosave/final-submit/dashboard
Pesan error:
Apakah peserta lain normal:
Tindakan panitia yang sudah dilakukan:
Butuh keputusan: tahan wave / lanjut / emergency review
```

## 14. Prinsip Keputusan

GO selama safe-mode direct stabil. NO-GO untuk hybrid/queue/runtime buffer, APK baru, load test production, heavy export saat ujian, dan deploy/restart production saat ujian aktif tanpa emergency approval eksplisit.
