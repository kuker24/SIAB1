# Fase D — Cutover VPS

**Tidak dijalankan.** Butuh permintaan operasional terpisah.

Jangan saat ujian live. Jangan `docker compose down -v`. Backup Postgres dulu.

Urutan nanti:

1. `--profile native-lean` Go shadow, Nginx tetap Python.
2. Satu lane uji ke `go_server`.
3. Parity autosave / SXB / JWT 120 / kiosk.
4. Pindah lane siswa, lalu admin.
5. `bash scripts/verify_stable_release_vps.sh`
6. APK Kotlin lewat `tools/build_native_kiosk_apk.sh`

Python dan Flutter belum dihapus.
