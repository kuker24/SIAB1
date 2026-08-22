plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "id.siab1.kiosk"
    compileSdk = 34

    defaultConfig {
        applicationId = "id.siab1.kiosk"
        minSdk = 26
        targetSdk = 34
        versionCode = 2
        versionName = "2.0.0"
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

    buildTypes {
        release {
            isMinifyEnabled = false
            isShrinkResources = false
            signingConfig = signingConfigs.getByName("debug")
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
