# APK Source Review - Ujian Online

Tanggal: 2026-06-02

Dokumen ini menjelaskan cakupan source code APK/mobile yang diupload ke GitHub untuk review AI dan perencanaan perombakan arsitektur beberapa bulan ke depan.

## Tujuan

1. Memungkinkan AI reviewer membaca source APK/mobile secara lengkap.
2. Memungkinkan analisis build configuration Android/Flutter.
3. Menghindari upload file besar, generated, credential, dan output build.
4. Menyediakan daftar file yang sengaja di-exclude agar tidak dianggap hilang.

## Folder source APK utama

```text
flutter_client_code/
```

Isi penting yang tersedia untuk review:

```text
flutter_client_code/lib/
flutter_client_code/lib/main.dart
flutter_client_code/lib/config.dart
flutter_client_code/lib/pages/
flutter_client_code/lib/services/
flutter_client_code/lib/widgets/
flutter_client_code/pubspec.yaml
flutter_client_code/pubspec.lock
flutter_client_code/analysis_options.yaml
flutter_client_code/sxb_dependencies.yaml
flutter_client_code/test/
flutter_client_code/android/app/build.gradle
flutter_client_code/android/build.gradle
flutter_client_code/android/settings.gradle
flutter_client_code/android/gradle.properties
flutter_client_code/android/gradle/wrapper/gradle-wrapper.properties
flutter_client_code/android/gradle/wrapper/gradle-wrapper.jar
flutter_client_code/android/gradlew
flutter_client_code/android/gradlew.bat
flutter_client_code/android/app/src/main/
flutter_client_code/android/app/src/debug/
flutter_client_code/android/app/src/profile/
flutter_client_code/windows_src/
```

## APK builder tooling

```text
tools/apk_builder_gui/
```

Isi penting:

```text
tools/apk_builder_gui/README.md
tools/apk_builder_gui/NOTE.txt
tools/apk_builder_gui/flutter_setup.py
tools/apk_builder_gui/requirements.txt
tools/apk_builder_gui/apk_builder_config.json
```

Catatan:

- `tools/apk_builder_core/` saat snapshot hanya berisi `__pycache__`, sehingga tidak diupload sebagai source penting.
- Jika source Python builder core ditemukan/dibuat ulang nanti, boleh ditambahkan.

## File yang sengaja tidak diupload

File berikut sengaja tidak diupload ke GitHub:

```text
apk_builds/
static/apk/
flutter_client_code/build/
flutter_client_code/.dart_tool/
flutter_client_code/android/.gradle/
flutter_client_code/.idea/
flutter_client_code/android/local.properties
flutter_client_code/android/key.properties
flutter_client_code/android/app/release-keystore.jks
*.apk
*.aab
*.jks
*.keystore
```

Alasan:

- Output APK/AAB besar dan bisa dibuat ulang.
- `.gradle`, `.dart_tool`, `.idea` adalah generated/local state.
- `local.properties` berisi path SDK lokal.
- `key.properties` dan keystore adalah credential signing APK.

## Informasi build penting

Project Flutter:

```text
name: ujian_online_seb
version: 1.0.0+1
Dart SDK: >=3.0.0 <4.0.0
```

Android config ringkas:

```text
applicationId: com.school.examapp
compileSdk: 36
targetSdk: 35
Java/Kotlin target: 17
minSdkVersion: flutter.minSdkVersion
release minifyEnabled: true
release shrinkResources: true
universal APK: enabled via ABI split disabled
```

Security/runtime features dari source:

```text
forceHttps: true
allowCleartextTraffic: false
enableKiosk: true
blockScreenshot: true
detectRoot: true
blockTaskSwitch: true
enableOfflineFirstRuntime: true
enableAdaptiveViolationDetection: true
answerJournalSyncIntervalSeconds: 6
answerJournalBatchSize: 80
```

## Catatan penting untuk AI reviewer

Tolong review area berikut:

1. Apakah interval sync journal `6s` terlalu agresif untuk traffic 300-600 siswa?
2. Apakah batch size `80` aman untuk DB/API saat banyak siswa?
3. Apakah autosave/journal punya exponential backoff dan jitter saat server `429/503/502`?
4. Apakah final submit cukup diprioritaskan dibanding autosave background?
5. Apakah violation detection/logging bisa dibuat best-effort/async agar tidak membebani DB?
6. Apakah offline-first storage sudah aman terhadap refresh, app close, dan retry?
7. Apakah WebView/security/kiosk handling aman untuk Android produksi?
8. Apakah signing/build process butuh standardisasi tanpa menyimpan secret di repo?

## Build command referensi

Dari folder project Flutter:

```bash
cd flutter_client_code
flutter pub get
flutter build apk --release
```

Jika menggunakan Gradle wrapper Android:

```bash
cd flutter_client_code/android
./gradlew assembleRelease
```

Catatan:

- Release signing memerlukan `key.properties` dan keystore lokal/CI secret yang tidak disimpan di repo.
- Untuk AI review, cukup cek source dan build config; jangan meminta credential signing.

## Prompt singkat untuk ChatGPT Connector

Review full APK/mobile source in:

```text
flutter_client_code/
tools/apk_builder_gui/
docs/APK_SOURCE_REVIEW_20260602.md
```

Focus on architecture changes for future scale, especially autosave/journal sync behavior under 300-600 concurrent exam users, final submit priority, offline-first reliability, Android security/kiosk behavior, and safe build/signing workflow. Do not request or expose signing keys, `.env`, tokens, or student data.
