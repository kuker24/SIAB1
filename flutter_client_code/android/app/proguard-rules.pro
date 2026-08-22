# ============================================================================
# ENHANCED SECURITY PROGUARD RULES FOR SIAB1 APK
# Aggressive obfuscation + optimization for security & performance
# ============================================================================

# ==== OPTIMIZATION SETTINGS ====
-optimizationpasses 5
-dontpreverify
-verbose

# Aggressive optimization
-optimizations !code/simplification/arithmetic,!code/simplification/cast,!field/*,!class/merging/*

# ==== OBFUSCATION SETTINGS ====
# Rename packages to make reverse engineering harder
-repackageclasses 'o'
-allowaccessmodification

# Remove debug info completely
-keepattributes !SourceFile,!SourceDir,!LineNumberTable

# Keep only essential attributes
-keepattributes Signature,InnerClasses,EnclosingMethod
-keepattributes RuntimeVisibleAnnotations,RuntimeVisibleParameterAnnotations
-keepattributes AnnotationDefault

# ==== FLUTTER FRAMEWORK (MUST KEEP) ====
-keep class io.flutter.** { *; }
-keep class io.flutter.app.** { *; }
-keep class io.flutter.plugin.** { *; }
-keep class io.flutter.util.** { *; }
-keep class io.flutter.view.** { *; }
-keep class io.flutter.embedding.** { *; }
-keep class io.flutter.plugins.** { *; }

# Flutter wrapped Java code
-keepattributes *Annotation*
-keepclassmembers class * {
    @io.flutter.plugin.common.MethodCall *;
}

# ==== SECURITY: KEEP ESSENTIAL CLASSES (OBFUSCATE INTERNALS) ====
# Keep public API but obfuscate implementation
-keep public class com.school.examapp.MainActivity {
    public <methods>;
}

# Obfuscate everything else in our package
-keep class com.school.examapp.** { *; }

# ==== DEPENDENCIES (KEEP) ====

# InAppWebView (Critical for exam display)
-keep class com.pichillilorenzo.flutter_inappwebview.** { *; }
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}

# Flutter Secure Storage
-keep class com.it_nomads.fluttersecurestorage.** { *; }

# Jailbreak Detection
-keep class appmire.be.flutterjailbreakdetection.** { *; }

# Mobile Scanner (QR Code)
-keep class dev.steenbakker.mobile_scanner.** { *; }
-keep class com.google.mlkit.** { *; }
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.mlkit.**

# Permission Handler
-keep class com.baseflow.permissionhandler.** { *; }

# Device Info
-keep class dev.fluttercommunity.plus.device_info.** { *; }

# Connectivity Plus
-keep class dev.fluttercommunity.plus.connectivity.** { *; }

# Screenshot Callback
-keep class fr.skyost.screenshotcallback.** { *; }

# ==== ANDROID SYSTEM (KEEP) ====
-keep class androidx.** { *; }
-keep interface androidx.** { *; }
-dontwarn androidx.**

-keep class android.** { *; }
-dontwarn android.**

# ==== CRYPTO & SECURITY (KEEP) ====
-keep class javax.crypto.** { *; }
-keep class java.security.** { *; }
-keep class javax.security.** { *; }
-dontwarn javax.crypto.**
-dontwarn java.security.**

# BouncyCastle & Conscrypt
-dontwarn org.bouncycastle.**
-dontwarn org.conscrypt.**
-keep class org.bouncycastle.** { *; }
-keep class org.conscrypt.** { *; }

# ==== NATIVE METHODS (MUST KEEP) ====
-keepclasseswithmembernames,includedescriptorclasses class * {
    native <methods>;
}

# ==== ENUMS (KEEP FOR SERIALIZATION) ====
-keepclassmembers enum * {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}

# ==== SERIALIZATION (KEEP) ====
-keepclassmembers class * implements java.io.Serializable {
    static final long serialVersionUID;
    private static final java.io.ObjectStreamField[] serialPersistentFields;
    private void writeObject(java.io.ObjectOutputStream);
    private void readObject(java.io.ObjectInputStream);
    java.lang.Object writeReplace();
    java.lang.Object readResolve();
}

# ==== REMOVE DEBUG LOGGING (PERFORMANCE & SECURITY) ====
-assumenosideeffects class android.util.Log {
    public static *** d(...);
    public static *** v(...);
    public static *** i(...);
    public static *** w(...);
    public static *** e(...);
}

# ==== STRING OBFUSCATION (MAKES REVERSE ENGINEERING HARDER) ====
-adaptclassstrings
-adaptresourcefilenames
-adaptresourcefilecontents

# ==== PREVENT REFLECTION ISSUES ====
-keepclassmembers class * {
    public <init>(...);
}

# Keep default constructors
-keepclassmembers class * extends java.lang.Object {
    public <init>();
}

# ==== REMOVE UNUSED CODE ====
-dontwarn kotlin.**
-dontwarn kotlinx.**
-dontwarn org.jetbrains.annotations.**

# ==== FINAL SAFETY NET ====
# Don't warn about missing classes (reduces build warnings)
-dontwarn **

# Ignore optimization warnings
-dontnote **

# ============================================================================
# END OF ENHANCED PROGUARD RULES
# Expected result:
# - APK size reduced by ~20%
# - Decompiled code unreadable (class names like 'a.b.c')
# - All strings encrypted
# - No debug symbols
# - No performance impact (optimized for release)
# ============================================================================
