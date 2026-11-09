// TEST FIXTURE, not a product: a tiny, clearly labelled APK that the DEV catalog (tools/dev_fixture.py) points at, so the installer can be tested end to end.
plugins { id("com.android.application") }

android {
    namespace = "app.retrohatch.testfixture"
    compileSdk = 34
    defaultConfig {
        applicationId = "app.retrohatch.testfixture"
        minSdk = 31
        targetSdk = 34
        versionCode = 7
        versionName = "1.0.0-fixture"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
