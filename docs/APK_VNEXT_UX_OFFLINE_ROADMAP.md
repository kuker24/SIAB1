# APK vNext Roadmap - UX First + Offline Continue

Tanggal: 2026-03-07  
Strategi: **UX dulu + offline continue penuh + deteksi hybrid adaptif**

## Scope Prioritas
1. Offline Exam Package (signed + encrypted)
2. Answer Journal lokal (append-only, encrypted)
3. Sync Engine idempotent (no duplicate/no loss)
4. Resume state kuat (crash/restart recovery)
5. Offline timer guard (anti manipulasi waktu)
6. Status koneksi jelas (Online/Degraded/Offline + indikator lokal)
7. Mode tidak terjebak (emergency exit aman + audit trail)
8. Antrian violation lokal + auto flush
9. Deteksi pelanggaran adaptif (risk score/cooldown/decay)
10. Paket diagnostik 1-tap (terenkripsi)

## Status Implementasi Saat Ini
| No | Item | Status | Catatan |
|---|---|---|---|
| 1 | Offline Exam Package | Done (v2) | Endpoint backend `offline-package` + hash/signature + cache encrypted di APK. |
| 2 | Answer Journal lokal | Done (v2) | Event bridge web->native (`answerJournalEvent`) + append-only encrypted journal. |
| 3 | Sync Engine idempotent | Done (v2) | Endpoint `answer-journal/sync` (event_id ack, duplicate-safe, retry backoff). |
| 4 | Resume state kuat | Done (v2) | Snapshot pointer soal/timer/state lokal + restore saat sesi aktif terdeteksi lagi. |
| 5 | Offline timer guard | Done (v2) | Timer guard native via `timerSync` + drift/anomali detection. |
| 6 | Status koneksi jelas | Done (v1) | Badge koneksi: Online/Degraded/Offline + indikator queue lokal. |
| 7 | Tidak terjebak saat outage | Done (v1) | Emergency exit policy adaptif + logging insiden. |
| 8 | Queue violation lokal | Done (v1) | Queue local + auto flush saat koneksi/token pulih. |
| 9 | Deteksi adaptif | Done (v1) | Risk score + cooldown + decay + threshold adaptif. |
| 10 | Diagnostik 1-tap | Done (v2) | Export diagnostic bundle terenkripsi (long-press badge / tombol error screen). |

## Konfigurasi Runtime Baru
- `resilienceProfile`: `ux_offline_first` / `balanced` / `strict_security`
- `reconnectProbeIntervalSeconds`
- `emergencyExitMinOutageMinutes`
- `emergencyExitMinFailedProbes`
- `riskAutoSubmitThreshold`
- `showConnectionBadge`

Semua parameter di atas digenerate dari `tools/apk_builder_gui.py` ke `flutter_client_code/lib/config.dart`.

## Target Kualitas (Gate)
1. Kehilangan jawaban = **0** untuk outage <= 30 menit.
2. Recovery setelah koneksi online kembali <= **10 detik**.
3. Resume app setelah crash/restart <= **5 detik**.
4. False positive pelanggaran turun >= **40%**.

## Next Execution Plan
### Phase D (Hardening Lapangan)
- Uji simulasi outage 5/10/30 menit + validasi kehilangan jawaban = 0.
- Uji restart paksa aplikasi saat sesi aktif (resume < 5 detik).
- Uji false-positive detector pada perpindahan app singkat.

### Phase E (Operasional Hari-H)
- Siapkan SOP pengawas untuk ambil diagnostic bundle saat insiden.
- Tambah panel ringkas di monitoring admin untuk status queue recovery APK.
