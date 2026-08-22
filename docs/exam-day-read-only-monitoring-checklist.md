# Exam-Day Read-Only Monitoring Checklist

Checklist ini untuk monitoring ujian aktif tanpa mutasi production. Monitoring hanya boleh read-only dan harus mendukung keputusan operasional: lanjut wave, tahan wave, kurangi dashboard, stop export, atau emergency review.

## 1. Prinsip Read-Only

Boleh melihat status/metrics/log trend. Tidak boleh mengubah service, env, data, schema, APK, atau traffic mode.

Prioritas pemantauan:

1. Final submit aman.
2. Jawaban siswa aman.
3. Login/start tidak spike massal.
4. Dashboard summary tidak membebani sistem.
5. Cheating detection tetap terlihat secara aggregate.

## 2. Yang Boleh Dipantau

### API health

- Health endpoint/status yang sudah ada.
- Apakah API merespons normal.
- Gejala timeout pada login/start/autosave/final-submit.

### 4xx/5xx trend

- Trend 5xx meningkat atau tidak.
- 429/4xx meningkat karena retry/spam atau auth issue.
- Pisahkan issue isolated vs banyak peserta.

### login/start/final-submit symptoms

- Login gagal massal atau isolated.
- Start exam lambat/gagal.
- Autosave retry sporadis atau meluas.
- Final submit lambat/timeout/gagal.

### DB connection pressure read-only

- Jumlah koneksi aktif/idle.
- Tanda query timeout/connection exhaustion.
- Tidak menjalankan query berat/reporting saat ujian aktif.

### Redis queue/backlog read-only

- Pending/processing/backlog counters jika tersedia.
- Dirty/backlog trend jika ada monitoring runtime.
- Jangan mengubah Redis key/data saat ujian aktif.

### Nginx error trend

- 5xx upstream trend.
- Timeout/gateway error trend.
- Jangan reload/restart Nginx tanpa emergency approval eksplisit.

### admin dashboard summary

- Summary/aggregate sessions.
- Summary/aggregate cheating/violation.
- Hindari detail banyak siswa.
- Hindari refresh agresif.

## 3. Yang Tidak Boleh Dilakukan

Dilarang saat ujian aktif tanpa emergency approval eksplisit:

- Restart service.
- Deploy code.
- Recreate container.
- Run migration.
- Run load test.
- Export/report berat.
- Enable queue/hybrid/runtime buffer.
- Build/distribute APK baru.
- Mengubah env production.
- Menghapus/mengubah data siswa.
- Mengubah endpoint contract.
- Mengubah DB schema.
- Melemahkan APK/SXB/security validation.
- Menghapus cheating detection.
- Menghapus emergency/admin command.

## 4. Decision Thresholds

### Jika 5xx naik

Keputusan default:

- Tahan wave login/start/submit berikutnya.
- Kurangi dashboard.
- Stop export/report.
- Catat incident severity minimal S2; S3 jika banyak peserta/final-submit terdampak.
- Emergency review jika tren tidak turun atau final-submit berisiko.

### Jika dashboard lambat tapi answer/final-submit normal

Keputusan default:

- Kurangi jumlah admin/tab dashboard.
- Gunakan summary-only.
- Jangan restart/deploy.
- Jangan membuka detail banyak siswa.
- Lanjut wave hati-hati hanya jika login/start/answer/final-submit normal.

### Jika final-submit lambat

Keputusan default:

- Tahan wave submit massal berikutnya.
- Stop export/report.
- Stop dashboard detail.
- Instruksikan siswa menunggu respons aplikasi.
- Jangan spam submit.
- Escalation cepat; severity minimal S3 jika meluas.

### Jika DB/API pressure

Keputusan default:

- Tahan wave.
- Kurangi dashboard.
- Stop export/report.
- Escalation ke backend/DevOps reviewer.
- Production action hanya jika emergency approved.

### Jika Redis/backlog meningkat

Keputusan default:

- Tetap safe-mode direct/off; jangan aktifkan queue/hybrid/runtime buffer.
- Tahan wave dan kurangi dashboard.
- Stop export/report.
- Escalation jika backlog berhubungan dengan answer/final-submit risk.

### Jika cheating monitoring lambat/degraded

Keputusan default:

- Tetap pantau aggregate bila tersedia.
- Jangan hapus cheating detection.
- Jangan refresh detail agresif.
- Jika answer/final-submit normal, prioritaskan jalur ujian dan catat follow-up setelah ujian.

## 5. Quick Decision Table

| Gejala | Keputusan awal | Escalation |
| --- | --- | --- |
| Semua normal | Lanjut wave 150–200 | Tidak |
| 1–3 siswa gagal login | Tangani lokal, lanjut hati-hati | Jika meluas |
| Banyak login/start timeout | Tahan wave | Ya |
| Dashboard lambat, answer normal | Kurangi dashboard | Jika memburuk |
| Autosave retry sporadis | Monitor, tahan jika meluas | Jika banyak peserta |
| Final submit lambat | Tahan wave, stop export/detail | Ya, S3 |
| 5xx naik | Tahan wave, stop export/detail | Ya |
| DB/API pressure | Tahan wave | Ya |
| Data safety risk | Stop wave | Ya, S4 |

## 6. Read-Only Report Template

```text
Jam:
Wave saat ini:
Peserta aktif perkiraan:
API health:
4xx/5xx trend:
Login/start symptoms:
Autosave/final-submit symptoms:
DB pressure:
Redis backlog:
Nginx error trend:
Dashboard summary status:
Cheating monitoring status:
Keputusan: lanjut wave / tahan wave / emergency review
Catatan:
```

## 7. End-of-Day Monitoring Handoff

```text
Tanggal:
Monitoring window:
Peak peserta:
Incident tertinggi: S0/S1/S2/S3/S4
Final submit status:
Answer safety concern: ya/tidak
Cheating monitoring: normal/degraded/blocked
Action yang ditahan sampai safe window:
Follow-up owner:
```
