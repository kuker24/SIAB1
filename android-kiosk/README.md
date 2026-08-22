# SIAB1 Android Kiosk

Native student exam APK. Exam content is HTML in WebView.

## Build

```bash
export SIAB1_SERVER_URL="https://your-domain.example/"
export SIAB1_RELEASE_KEYSTORE="$HOME/.android/siab1-release.jks"
export SIAB1_RELEASE_STORE_PASSWORD="..."
export SIAB1_RELEASE_KEY_ALIAS="..."
export SIAB1_RELEASE_KEY_PASSWORD="..."
./gradlew :app:assembleRelease
```

APK: `app/build/outputs/apk/release/app-release.apk`

Requires Android SDK (`ANDROID_HOME` or `local.properties` `sdk.dir`).
The release server URL and signing credentials are required through environment variables and must never be committed.
Release builds reject the `siab1.invalid` placeholder.
If `gradle/wrapper/gradle-wrapper.jar` is missing, the `./gradlew` script downloads Gradle 8.7 and runs the build.
