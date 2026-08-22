# 🤖 APK Builder GUI - Standalone Tool

Build Android APK **SIAB1** dari PC lokal dengan GUI.

## ⚡ Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Jalankan aplikasi
python apk_builder_gui.py
```

## 📋 Prasyarat

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.8+ | 3.10+ |
| RAM | 4GB | 8GB+ |
| Disk | 10GB free | 20GB+ |
| Flutter SDK | 3.0+ | Latest stable |
| Android SDK | API 33 | Latest |

### Install Flutter SDK

1. Download: https://flutter.dev/docs/get-started/install
2. Extract ke folder (misal: `C:\flutter`)
3. Tambahkan ke PATH:
   ```
   C:\flutter\bin
   ```
4. Verifikasi:
   ```bash
   flutter doctor
   ```

## 🎯 Cara Penggunaan

### Tab 1: Konfigurasi

1. **Nama Aplikasi** - Nama yang muncul di launcher Android
2. **Package Name** - Unique identifier (contoh: `com.sekolah.ujian`)
3. **Server URL** - URL server SIAB1 Anda
4. **Icon** - Upload PNG 512x512 (opsional)
5. **Flutter Project** - Pilih folder `flutter_client_code` dari server

### Tab 2: Build APK

1. Klik **"Cek Flutter"** - Pastikan Flutter terinstall
2. Klik **"BUILD APK"** - Mulai proses build
3. Tunggu ~5-10 menit
4. APK akan tersimpan di folder `build/`

## 📁 Struktur Output

```
flutter_client_code/
└── build/
    ├── app/outputs/flutter-apk/app-release.apk  # APK asli
    └── NamaAplikasi_YYYYMMDD_HHMMSS.apk         # APK dengan nama custom
```

## 🔧 Troubleshooting

| Error | Solusi |
|-------|--------|
| Flutter not found | Install Flutter SDK dan tambahkan ke PATH |
| Android SDK not found | Install Android Studio |
| Build failed | Cek log untuk detail error |
| Out of memory | Butuh RAM minimal 8GB |

## 💾 Export/Import Config

- **Simpan Config**: Simpan konfigurasi saat ini
- **Export Config**: Export ke file JSON untuk backup
- **Load Config**: Import dari file JSON

Config disimpan di: `apk_builder_config.json`

## 📞 Support

Jika ada masalah, hubungi administrator sistem.
