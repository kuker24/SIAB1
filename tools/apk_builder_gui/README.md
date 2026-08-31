# APK Builder GUI

Build APK native **android-kiosk** (`id.siab1.kiosk`) dari PC lokal.

## Quick Start

Dari root repo:

```bash
python3 tools/apk_builder_gui.py
```

atau:

```bash
bash bin/run_apk_builder.sh
```

## Prasyarat

| Requirement | Minimum |
|-------------|---------|
| Python | 3.11 |
| JDK | 17 |
| Android SDK | API 34 |
| Signing env | `~/.android/siab1-release.env` |

Flutter SDK tidak diperlukan untuk kiosk native.

Signing env wajib berisi `SIAB1_RELEASE_KEYSTORE`, `SIAB1_RELEASE_STORE_PASSWORD`, `SIAB1_RELEASE_KEY_ALIAS`, `SIAB1_RELEASE_KEY_PASSWORD`. Jangan commit file ini.

## Cara pakai

1. Isi Server URL production. Placeholder `siab1.invalid` ditolak.
2. Version name/code mengikuti `android-kiosk`.
3. **Simpan Konfigurasi** atau langsung **Build Artifact**.
4. Output: `apk_builds/siab1_kiosk_YYYYMMDD_HHMMSS.apk`
5. Daftarkan build token dan SHA-256 di Admin Panel.

Build Artifact = `assembleRelease`. Sideload saja, bukan Play Store.

## Troubleshooting

| Error | Solusi |
|-------|--------|
| Signing rilis belum siap | Isi `~/.android/siab1-release.env` |
| JDK 17 tidak ditemukan | Install Temurin 17, set `JAVA_HOME` |
| Android SDK tidak ditemukan | Set `ANDROID_HOME` |
| Placeholder URL | Ganti `siab1.invalid` dengan host production |
