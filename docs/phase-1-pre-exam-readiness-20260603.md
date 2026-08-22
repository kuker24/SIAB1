# Phase 1 Pre-Exam Readiness — 2026-06-03

Dokumen ini adalah checklist kesiapan sebelum/saat ujian aktif. Scope Phase 1 adalah **local/GitHub readiness only**: tidak deploy ke VPS, tidak restart service production, tidak build APK baru, dan tidak mengubah production safe-mode.

## 1. Production Safe-Mode Baseline

Production harus tetap pada baseline aman berikut selama ujian aktif:

```text
ANSWER_WRITE_MODE=direct
ANSWER_QUEUE_ENABLED=false
ANSWER_QUEUE_PERCENTAGE=0
EXAM_PEAK_MODE=true
VIOLATION_ASYNC_ENABLED=true
ADMIN_MONITORING_DETAIL_LEVEL=summary
MOBILE_APK_PRIMARY=true
SEB_DESKTOP_LEGACY_ENABLED=false
SEB_QR_ENABLED=false
SEB_DEBUG_ENDPOINTS_ENABLED=false
APK_BUILD_ENDPOINT_ENABLED=false
TELEGRAM_ALERTING_ENABLED=false
HEAVY_EXPORT_ENABLED=false
```

Prinsip utama:

- Runtime utama: APK Android/HP yang sudah ada.
- Final submit adalah prioritas tertinggi.
- Jawaban siswa harus aman dengan write path direct.
- Cheating/violation detection tetap aktif, tetapi aggregate-first, async, cached, dan tidak membebani answer/final-submit path.
- Admin dashboard digunakan summary-only.

## 2. Yang Boleh Dilakukan Saat Ujian Aktif

Hanya aktivitas operasional rendah risiko:

- Monitoring read-only: health, resource usage, log error rate, status container tanpa restart.
- Membuka admin dashboard dalam mode summary.
- Membantu siswa login ulang secara prosedural tanpa menghapus data atau sesi.
- Mengarahkan peserta masuk/start/submit bertahap.
- Mencatat incident timeline dan jumlah peserta terdampak.
- Menghubungi escalation owner jika ada gejala 5xx/DB/Redis/API pressure.

## 3. Yang Dilarang Saat Ujian Aktif

NO-GO selama ujian aktif tanpa approval emergency eksplisit:

- Deploy code ke VPS production.
- Restart service, recreate container, atau restart DB/Redis/Nginx.
- Run migration production.
- Run load test ke production.
- Mengaktifkan `ANSWER_WRITE_MODE=hybrid`, `ANSWER_WRITE_MODE=queue`, `ANSWER_QUEUE_ENABLED=true`, atau runtime buffer.
- Build/distribute APK baru.
- Mengaktifkan `APK_BUILD_ENDPOINT_ENABLED=true`.
- Mengubah APK signature/header/SXB/SEB validation.
- Menghapus cheating detection atau emergency/admin command.
- Export/report berat saat ujian.
- Mengubah public endpoint contract.
- Mengubah DB schema production.

## 4. GO/NO-GO Criteria

### GO

- Production tetap mobile-first safe-mode direct.
- Existing APK digunakan dan physical smoke test 1–3 HP Android nyata pass.
- Peserta masuk bertahap 150–200 orang per gelombang.
- Admin hanya membuka dashboard summary.
- Final submit dilakukan bertahap, tidak semua peserta menunggu detik terakhir.
- Tidak ada rencana deploy/restart/build/load-test selama ujian aktif.

### NO-GO

- Hybrid/queue/runtime buffer diaktifkan.
- APK baru dibuild/distribute menjelang atau saat ujian.
- Load test production.
- Export/report berat saat ujian.
- Dashboard detail/refresh agresif dipakai saat peak.
- Banyak 5xx/timeout pada login/start/answer/final-submit dan belum ada mitigasi.
- Physical APK smoke test gagal pada login, join token, start exam, answer save, atau final submit.

## 5. Physical APK Smoke Test Checklist Ringkas

Dilakukan panitia/operator pada 1–3 HP Android nyata dengan APK existing, bukan APK baru:

- [ ] Buka APK existing.
- [ ] Login siswa synthetic/test yang disediakan panitia, bukan akun siswa real jika tidak perlu.
- [ ] Join token ujian test/staging/local atau jadwal smoke yang aman.
- [ ] Start exam berhasil.
- [ ] Timer berjalan dan tidak reset.
- [ ] Jawab beberapa soal, pindah soal, kembali, jawaban tetap ada.
- [ ] Autosave/retry ringan terlihat normal.
- [ ] Final submit berhasil satu kali.
- [ ] Result/grading tampil sesuai konfigurasi ujian.
- [ ] Screenshot/task switch/root/tamper detection tetap bekerja sesuai policy.
- [ ] Emergency exit/admin command tetap tersedia untuk skenario panitia.
- [ ] Cheating/violation muncul di admin dashboard aggregate/summary.

Detail lengkap ada di `docs/physical-mobile-smoke-test-checklist.md`.

## 6. Backend Smoke Checklist

Backend smoke test **tidak boleh diarahkan ke production saat ujian aktif**. Jalankan hanya di staging/local atau setelah ujian tidak aktif dan ada approval.

Checklist aman:

- [ ] Login teacher/test user.
- [ ] Login student synthetic.
- [ ] Join token synthetic.
- [ ] Start exam synthetic.
- [ ] Submit answer beberapa soal.
- [ ] Final submit synthetic.
- [ ] Cek monitoring summary page.
- [ ] Cek runtime policy endpoint.
- [ ] Cleanup data synthetic dan verifikasi residue 0.

## 7. Admin Dashboard Usage Rule

Saat ujian aktif:

- Gunakan hanya dashboard summary/aggregate.
- Jangan membuka detail banyak siswa secara paralel.
- Jangan melakukan refresh agresif.
- Jangan export PDF/Excel/report berat.
- Cheating detection tetap dipantau melalui aggregate-first dashboard.
- Jika dashboard lambat tetapi answer/final-submit normal, prioritaskan answer/final-submit dan kurangi penggunaan dashboard.

## 8. Participant Wave Plan

Rencana masuk peserta:

1. Gelombang 1: 150–200 peserta login.
2. Tunggu stabil 2–5 menit: login success, error rate, API/DB/Redis pressure.
3. Gelombang berikutnya: 150–200 peserta.
4. Start exam juga bertahap, jangan semua klik start bersamaan.
5. Final submit bertahap: instruksikan peserta submit saat selesai, jangan menunggu detik terakhir bersama-sama.

Jika ada gejala 5xx/timeout meningkat, tahan gelombang berikutnya sampai kondisi stabil.

## 9. Final-Submit Safety Rule

Final submit adalah jalur prioritas tertinggi:

- Jangan menjalankan export/report/dashboard detail saat final-submit peak.
- Jangan restart/deploy saat banyak sesi mendekati selesai.
- Jika final submit lambat, minta siswa menunggu respons aplikasi; jangan spam tombol submit.
- Jika perlu eskalasi, catat waktu, username/session, exam, dan status yang terlihat tanpa mengambil data jawaban real ke luar sistem.

## 10. Export/Report Restriction

Selama ujian aktif:

- Heavy export/report harus off pada peak mode.
- Panitia menunda PDF/Excel/rekap besar sampai setelah final submit selesai.
- Jika laporan dibutuhkan mendesak, gunakan summary ringan atau tunggu safe window.

## 11. Rollback Instruction

Karena Phase 1 tidak melakukan deploy, rollback local/GitHub cukup dengan revert commit readiness jika diperlukan.

Jika di masa depan ada emergency production yang disetujui:

1. Konfirmasi incident dan approval eksplisit.
2. Prioritaskan mitigasi paling kecil dan reversible.
3. Jangan ubah DB schema saat ujian aktif.
4. Jangan aktifkan hybrid/queue/runtime buffer sebagai rollback cepat.
5. Pertahankan env direct/off.
6. Catat command, waktu, operator, dampak, dan hasil verifikasi.

## 12. Escalation Flow

1. Panitia kelas: kumpulkan gejala dan jumlah siswa terdampak.
2. Operator ujian: cek dashboard summary dan instruksi wave/submit.
3. Backend/DevOps reviewer: analisis read-only log/metrics bila diminta.
4. Decision owner/kepala panitia: memberi approval eksplisit jika emergency action diperlukan.
5. Setelah incident: buat timeline dan follow-up action tanpa mengubah data siswa.

## 13. Phase 1 Confirmation

Dokumen ini hanya readiness/runbook. Tidak ada instruksi untuk deploy, restart, migration, load test production, build APK, schema change, endpoint contract change, atau activation hybrid/queue/runtime buffer.
