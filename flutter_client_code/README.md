# SIAB1 Flutter Fallback

Klien Flutter dipertahankan sebagai fallback untuk SIAB1. Klien utama adalah Android kiosk native di `android-kiosk/`.

## Kontrak

- Application ID: `id.siab1.flutter`
- Entry point: `lib/main.dart`
- Konfigurasi: `lib/config.dart`
- Domain release harus menggantikan placeholder `siab1.invalid` melalui APK Builder sebelum build.

## Verifikasi

```bash
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
```

Keystore, `key.properties`, build output, dan credential lain harus tetap di luar Git.
