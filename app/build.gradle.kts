plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "tv.diagnostic"
    compileSdk = 35

    defaultConfig {
        applicationId = "tv.diagnostic.cs2352p687"
        minSdk = 26
        targetSdk = 28
        versionCode = 210
        versionName = "2.1.0"
    }
}

dependencies {
    implementation("com.google.zxing:core:3.5.3")
}

kotlin { jvmToolchain(17) }
