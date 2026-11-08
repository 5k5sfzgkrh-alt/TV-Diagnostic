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
        versionCode = 201
        versionName = "2.0.1"
    }
}

dependencies {
    implementation("com.google.zxing:core:3.5.3")
}

kotlin { jvmToolchain(17) }
