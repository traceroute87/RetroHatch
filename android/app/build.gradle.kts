plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "app.retrohatch.rotate"
    compileSdk = 34

    defaultConfig {
        applicationId = "app.retrohatch.rotate"
        minSdk = 31          // RG Rotate: Android 12 (API 31)
        targetSdk = 34
        versionCode = 2
        versionName = "0.4.0-ui"
    }

    buildTypes {
        release { isMinifyEnabled = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    sourceSets {
        // The unit tests verify the SAME signed fixture the Nano's Python and C verifiers use (tests/trust_fixture/signed).
        getByName("test").resources.srcDir(rootProject.projectDir.parentFile.resolve("tests/trust_fixture/signed"))
    }
    testOptions { unitTests.isReturnDefaultValues = true }
    lint { abortOnError = false }
}

dependencies {
    implementation("org.bouncycastle:bcprov-jdk18on:1.78.1")   // Ed25519 (Android 12 has no java.security Ed25519); no custom crypto
    testImplementation("junit:junit:4.13.2")
}
