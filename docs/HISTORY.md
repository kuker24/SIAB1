# Riwayat Ringkas SIAB1

Repository ini dikonsolidasikan dari implementasi lama menjadi SIAB1 dengan history Git kanonis yang bersih.

## Perubahan Utama

- Backend FastAPI di-hardening untuk autentikasi, rate limiting, audit, autosave, submit, recovery, dan operasi asesmen.
- Jalur Go Native-Lean ditambahkan untuk route utama dengan fallback FastAPI.
- Android kiosk native menjadi klien utama; Flutter dipertahankan sebagai fallback.
- Frontend monolit dipecah menjadi module dengan bundle reproducible.
- Monitoring, backup, capacity guard, dan release gate ditambahkan.
- Branding, identifier database/container, package client, dokumentasi, dan tooling dikonsolidasikan ke SIAB1.

Phase report dan snapshot VPS lama dihapus dari branch aktif setelah fakta yang masih berlaku dipindahkan ke dokumentasi kanonis. Detail sebelumnya tetap dapat ditelusuri melalui riwayat Git sebelum konsolidasi dokumentasi.
