# Ujian Online Jules Up5 V1

Entry point dokumentasi agar konteks proyek tetap tunggal dan mudah dinavigasi.

## Sumber Konteks Aktif

1. `AGENTS.md` — aturan, peta proyek, dan batas operasional yang tahan lama.
2. `.pi/HANDOFF.md` — satu-satunya checkpoint pekerjaan aktif atau sementara.
3. Kode dan manifest aktual — sumber fakta runtime yang otoritatif.

Handoff, snapshot, save, atau progress note lain dianggap historis kecuali `.pi/HANDOFF.md` secara eksplisit mengaktifkannya.

## Referensi Pendukung

- `ARCHITECTURE.md` — gambaran arsitektur historis; beberapa detail dapat tertinggal.
- `CODEBASE.md` — peta kode historis; verifikasi terhadap source aktual.
- `DEPLOYMENT.md` — referensi deployment dengan drift yang dicatat di `AGENTS.md`.
- `plans/README.md` — indeks rencana bila tersedia.
- `docs/` — runbook, laporan validasi, dan dokumentasi historis.
- `reports/` — hasil pemeriksaan lokal bila tersedia.

## Catatan

- Konsolidasi konteks tidak mengubah endpoint, schema database, flow APK, atau runtime aplikasi.
- Untuk operasi production, validasi kondisi VPS secara langsung sebelum bertindak.
