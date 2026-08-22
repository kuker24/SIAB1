# Phase 2 Exam-Day Operation Control — 2026-06-03

Dokumen ini adalah kontrol operasional saat ujian aktif. Tujuannya menjaga stabilitas ujian dengan wave control, monitoring read-only, incident logging, dan keputusan GO/NO-GO tanpa perubahan production.

## 1. Tujuan Phase 2

Prioritas operasional:

1. Final submit aman.
2. Jawaban siswa aman.
3. Login/start exam tidak spike massal.
4. Admin dashboard hanya summary/aggregate.
5. Cheating detection tetap terlihat di dashboard admin.
6. Tidak ada deploy/restart/migration/load test production saat ujian aktif.
7. Tidak ada APK baru.
8. Tidak ada hybrid/queue/runtime buffer.

## 2. Safe-Mode Baseline Wajib

Production harus tetap pada baseline berikut:

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

Jika ada gejala incident, mitigasi operasional pertama adalah **tahan wave, kurangi dashboard, stop export, dan escalation** — bukan mengaktifkan queue/hybrid/runtime buffer.

## 3. Peran dan Tanggung Jawab

### Panitia ruang/kelas

- Mengatur peserta login/start/final-submit bertahap.
- Mencatat gejala siswa terdampak.
- Mengarahkan siswa tidak spam login/start/submit.
- Tidak meminta install APK baru saat ujian aktif.

### Operator ujian

- Menjaga wave control 150–200 peserta.
- Memantau dashboard summary dan status read-only.
- Menentukan lanjut wave/tahan wave berdasarkan gejala.
- Menyiapkan incident log jika ada masalah.

### Backend/DevOps reviewer

- Memberi rekomendasi berdasarkan read-only metrics/log/status jika diminta.
- Tidak melakukan deploy/restart/recreate/migration/load-test tanpa emergency approval eksplisit.
- Memprioritaskan answer/final-submit safety.

### Decision owner

- Menentukan GO/NO-GO operasional jika incident S3/S4.
- Memberi approval eksplisit jika emergency action production benar-benar diperlukan.
- Menyetujui handoff/follow-up setelah ujian.

## 4. Wave Control 150–200 Peserta

Gunakan gelombang untuk semua fase berat:

- Login: 150–200 peserta per gelombang.
- Start exam: bertahap per ruang/kelas, jangan satu detik bersamaan.
- Final submit: peserta submit saat selesai, jangan menunggu akhir bersama-sama.

Tahan gelombang berikutnya jika:

- 5xx/timeout meningkat.
- Banyak login/start gagal dalam satu ruang.
- Final-submit lambat/berisiko.
- DB/API pressure terlihat dari read-only monitoring.

## 5. Login Wave Procedure

1. Buka login untuk gelombang pertama 150–200 peserta.
2. Tunggu 2–5 menit untuk melihat stabilitas.
3. Lanjut gelombang berikutnya hanya jika login normal dan tidak ada spike error.
4. Jika siswa gagal login isolated, tangani lokal.
5. Jika banyak siswa gagal login, tahan wave dan escalation.

Instruksi ke siswa:

- Jangan login dari banyak perangkat.
- Jangan spam tombol login.
- Tunggu 15–30 detik sebelum retry jika timeout.

## 6. Start Exam Wave Procedure

1. Instruksikan start exam bertahap per ruang/kelas.
2. Hindari semua peserta klik start di detik yang sama.
3. Jika start lambat, minta siswa menunggu respons aplikasi.
4. Jangan refresh/spam tombol start.
5. Jika start failure terjadi massal, tahan wave dan escalation.

## 7. During-Exam Monitoring Procedure

Monitoring hanya read-only:

- API health/status.
- Trend 4xx/5xx.
- Gejala login/start/autosave/final-submit.
- DB connection pressure read-only.
- Redis queue/backlog read-only.
- Nginx error trend.
- Admin dashboard summary.

Operasional selama ujian:

- Admin dashboard summary-only.
- Jangan membuka detail banyak siswa secara paralel.
- Jangan refresh agresif.
- Stop export/report berat.
- Jika dashboard lambat tapi answer/final-submit normal, kurangi dashboard dan jangan restart.

## 8. Final Submit Procedure

Final submit adalah prioritas tertinggi.

1. Minta siswa submit saat selesai, bertahap.
2. Jangan menunggu detik terakhir untuk submit massal.
3. Jika final submit lambat, siswa menunggu respons aplikasi dan tidak spam submit.
4. Stop export dan dashboard detail selama final-submit peak.
5. Jika banyak final submit gagal/lambat, severity minimal S3 dan butuh emergency review.

## 9. Admin Dashboard Rule: Summary-Only

Saat ujian aktif:

- Gunakan dashboard summary/aggregate saja.
- Hindari detail banyak siswa.
- Hindari refresh agresif.
- Jangan export berat.
- Jika dashboard mengganggu stabilitas, kurangi jumlah admin yang membuka dashboard.

## 10. Cheating Detection Monitoring Rule

Cheating detection wajib tetap ada, tetapi dipantau secara aggregate-first:

- Pantau summary/aggregate violation dashboard.
- Jangan membuka detail violation secara masif saat peak.
- Jika cheating monitoring lambat tetapi answer/final-submit normal, jangan restart; kurangi dashboard dan catat incident.
- Jika jalur public violation sedang dished/mitigated oleh Nginx emergency, jangan ubah saat ujian aktif tanpa approval eksplisit; catat status dan follow-up setelah ujian.

## 11. Export/Report Restriction

Selama ujian aktif:

- `HEAVY_EXPORT_ENABLED=false` pada production safe-mode.
- Jangan export PDF/Excel/rekap besar.
- Jangan menjalankan report berat saat login/start/final-submit peak.
- Tunda laporan sampai ujian selesai atau safe window.

## 12. Incident Severity Levels

| Severity | Definisi | Contoh | Keputusan default |
| --- | --- | --- | --- |
| S0 | Normal | Ujian berjalan stabil | Lanjut wave sesuai rencana |
| S1 | Minor isolated issue | 1–3 siswa gagal login karena kredensial/jaringan lokal | Tangani lokal, lanjut wave jika sistem normal |
| S2 | Multiple students affected, answer/final-submit mostly normal | Beberapa siswa satu ruang timeout, dashboard lambat, autosave retry sporadis | Tahan wave sementara, kurangi dashboard, escalation ringan |
| S3 | Many 5xx atau final-submit risk | Banyak 5xx, start/answer/final-submit lambat massal | Tahan wave, stop export/dashboard detail, emergency review |
| S4 | Critical outage atau data safety risk | Final submit gagal massal, jawaban berisiko hilang, API/DB outage | Stop wave, emergency decision owner, production action hanya jika approved |

## 13. Action Matrix

| Kondisi | Lanjut wave | Tahan wave | Kurangi dashboard | Stop export | Emergency review |
| --- | --- | --- | --- | --- | --- |
| S0 normal | Ya | Tidak | Opsional | Ya, tetap stop export berat | Tidak |
| S1 isolated | Ya, jika tidak meluas | Tidak/opsional | Opsional | Ya | Tidak |
| S2 multiple affected | Tidak sampai stabil | Ya | Ya | Ya | Jika memburuk |
| Dashboard lambat, answer normal | Ya hati-hati | Opsional | Ya | Ya | Tidak langsung |
| 5xx meningkat | Tidak | Ya | Ya | Ya | Ya jika berlanjut |
| Final submit lambat/timeout | Tidak | Ya | Ya | Ya | Ya |
| DB/API pressure | Tidak | Ya | Ya | Ya | Ya |
| Data safety risk | Tidak | Ya | Ya | Ya | Ya, S4 |

## 14. Explicit Forbidden Actions Saat Ujian Aktif

Dilarang tanpa emergency approval eksplisit:

- Deploy ke VPS production.
- Restart API, DB, Redis, Nginx, pgbouncer, Celery.
- Recreate container.
- Run migration production.
- Run load test production.
- Mengubah env production.
- Enable hybrid/queue/runtime buffer.
- Build/distribute APK baru.
- Upload APK/AAB.
- Export/report berat saat peak.
- Menghapus/mengubah data siswa.
- Mengubah endpoint contract.
- Mengubah DB schema.
- Melemahkan APK/SXB/security validation.
- Menghapus cheating detection.
- Menghapus emergency/admin command.

## 15. Escalation Template

Gunakan template singkat ini di kanal operasional:

```text
Severity: S0/S1/S2/S3/S4
Tanggal/jam:
Ruang/kelas:
Jumlah peserta terdampak:
Fitur terdampak: login/start/autosave/final-submit/dashboard/cheating-monitoring
Gejala:
Endpoint jika diketahui:
Apakah peserta lain normal:
Status answer/final-submit:
Read-only indikator yang terlihat:
Tindakan panitia:
Tindakan operator:
Keputusan: lanjut wave / tahan wave / emergency review
Approval jika ada:
Butuh bantuan:
```

## 16. End-of-Day Handoff Notes

Setelah ujian selesai:

- Ringkas total peserta, gelombang, dan durasi.
- Catat incident S1–S4 dengan link/isi incident log.
- Catat apakah final submit selesai aman.
- Catat apakah cheating monitoring terlihat sesuai ekspektasi.
- Catat follow-up teknis yang ditunda sampai safe window.
- Jangan melakukan deploy/build/APK/report berat sebelum ada keputusan after-exam yang jelas.

Template handoff:

```text
Tanggal ujian:
Total peserta:
Gelombang login/start:
Final submit selesai: ya/tidak
Incident tertinggi: S0/S1/S2/S3/S4
Cheating monitoring: normal/degraded/blocked
Action yang ditunda:
Rekomendasi besok:
Approval/follow-up owner:
```

## 17. Operational Decision Phase 2

GO:

- Production tetap mobile-first safe-mode direct.
- Peserta masuk/start bertahap 150–200 orang.
- Admin hanya dashboard summary.
- Final submit bertahap.
- Existing APK digunakan.
- Monitoring hanya read-only.

NO-GO:

- Hybrid/queue/runtime buffer.
- APK baru.
- Load test production.
- Export/report berat saat ujian aktif.
- Deploy/restart production tanpa emergency approval eksplisit.
