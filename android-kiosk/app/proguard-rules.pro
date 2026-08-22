-keep class id.siab1.kiosk.web.Siab1Bridge { *; }
-keepclassmembers class id.siab1.kiosk.web.Siab1Bridge {
    @android.webkit.JavascriptInterface <methods>;
}
-keepattributes JavascriptInterface
-dontwarn okhttp3.**
-dontwarn okio.**
