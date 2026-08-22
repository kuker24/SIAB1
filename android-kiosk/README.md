# SIAB1 Android Kiosk

Native student exam APK. Exam content is HTML in WebView.

## Build

```bash
./gradlew :app:assembleRelease
```

APK: `app/build/outputs/apk/release/app-release.apk`

Requires Android SDK (`ANDROID_HOME` or `local.properties` `sdk.dir`).
If `gradle/wrapper/gradle-wrapper.jar` is missing, the `./gradlew` script downloads Gradle 8.7 and runs the build.
