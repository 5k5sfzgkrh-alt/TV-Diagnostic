plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "tv.diagnostic"
    compileSdk = 35

    defaultConfig {
        applicationId = "tv.diagnostic"
        minSdk = 26
        targetSdk = 28
        versionCode = 200
        versionName = "2.0.0"
    }
}

kotlin { jvmToolchain(17) }
