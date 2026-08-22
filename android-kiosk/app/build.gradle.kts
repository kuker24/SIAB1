import java.net.URI

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val releaseStoreFile = providers.environmentVariable("SIAB1_RELEASE_KEYSTORE").orNull
val releaseStorePassword = providers.environmentVariable("SIAB1_RELEASE_STORE_PASSWORD").orNull
val releaseKeyAlias = providers.environmentVariable("SIAB1_RELEASE_KEY_ALIAS").orNull
val releaseKeyPassword = providers.environmentVariable("SIAB1_RELEASE_KEY_PASSWORD").orNull
val siab1ServerUrl = providers.environmentVariable("SIAB1_SERVER_URL")
    .orElse("https://siab1.invalid/")
    .get()
val escapedServerUrl = siab1ServerUrl.replace("\\", "\\\\").replace("\"", "\\\"")
val releaseServerReady = runCatching { URI(siab1ServerUrl) }
    .getOrNull()
    ?.let { uri ->
        uri.scheme.equals("https", ignoreCase = true) &&
            !uri.host.isNullOrBlank() &&
            !uri.host.equals("siab1.invalid", ignoreCase = true) &&
            uri.userInfo == null &&
            uri.query == null &&
            uri.fragment == null
    } == true
val releaseSigningReady = listOf(
    releaseStoreFile,
    releaseStorePassword,
    releaseKeyAlias,
    releaseKeyPassword,
).all { !it.isNullOrBlank() }

android {
    namespace = "id.siab1.kiosk"
    compileSdk = 34

    defaultConfig {
        applicationId = "id.siab1.kiosk"
        minSdk = 26
        targetSdk = 34
        versionCode = 4
        versionName = "2.0.2"
        buildConfigField("String", "SIAB1_SERVER_URL", "\"$escapedServerUrl\"")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
        buildConfig = true
    }

    signingConfigs {
        create("release") {
            if (releaseSigningReady) {
                storeFile = file(requireNotNull(releaseStoreFile))
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            isShrinkResources = false
            signingConfig = signingConfigs.getByName("release")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
        debug {
            isMinifyEnabled = false
        }
    }

    packaging {
        resources {
            excludes += setOf("META-INF/LICENSE", "META-INF/NOTICE", "META-INF/*.kotlin_module")
        }
    }

    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

tasks.configureEach {
    if (name.contains("Release", ignoreCase = true)) {
        doFirst {
            check(releaseSigningReady) {
                "Release signing requires SIAB1_RELEASE_KEYSTORE and SIAB1_RELEASE_* credentials"
            }
            check(releaseServerReady) {
                "Release build requires a valid HTTPS SIAB1_SERVER_URL without credentials, query, or fragment"
            }
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.activity:activity-ktx:1.9.2")
    implementation("androidx.webkit:webkit:1.11.0")
    implementation("androidx.security:security-crypto:1.0.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
