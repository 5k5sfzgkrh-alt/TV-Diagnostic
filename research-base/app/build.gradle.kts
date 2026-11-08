plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.tvdiagnostic.hi3751"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.tvdiagnostic.hi3751.v133"
        minSdk = 23
        targetSdk = 28
        versionCode = 133
        versionName = "1.3.3"
    }

    kotlinOptions { jvmTarget = "1.8" }
}
