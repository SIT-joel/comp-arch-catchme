plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
}

android {
    namespace = "com.catchme.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.catchme.app"
        minSdk = 26 // covers both demo phones once OS versions are recorded
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        // Local development server; replace with the deployed HTTPS URL.
        // The LAN IP is the default: verified reachable from both bench phones
        // (Windows Firewall does NOT block inbound 8000, tested 9 Nov). The
        // 127.0.0.1 alternative rides an `adb reverse tcp:8000 tcp:8000`
        // tunnel, but wireless-adb reconnects have repeatedly broken that
        // tunnel mid-session; a launch intent extra "api_base" overrides this
        // default without a rebuild.
        // Stable public URL via the Cloudflare tunnel (infra compose runs
        // cloudflared; the dashboard routes the hostname to the host API).
        val envFile = rootProject.file("../infra/.env")
        val envProps = mutableMapOf<String, String>()
        if (envFile.exists()) {
            envFile.readLines().forEach { raw ->
                val line = raw.trim()
                if (line.isNotEmpty() && !line.startsWith("#") && line.contains("=")) {
                    val idx = line.indexOf('=')
                    envProps[line.substring(0, idx).trim()] = line.substring(idx + 1).trim()
                }
            }
        }
        val subdomain = envProps["SUBDOMAIN"]?.takeIf { it.isNotEmpty() } ?: "catchme.12357895.xyz"
        val cfId = (envProps["CLIENT_ID"] ?: "").replace("\"", "")
        val cfSecret = (envProps["CLIENT_SECRET"] ?: "").replace("\"", "")
        buildConfigField("String", "API_BASE", "\"https://$subdomain\"")
        // Cloudflare Access service token headers loaded from gitignored
        // infra/.env at local build time (never committed in source); launch
        // intent extras "cf_id"/"cf_secret" can still override them per device.
        buildConfigField("String", "CF_ACCESS_ID", "\"$cfId\"")
        buildConfigField("String", "CF_ACCESS_SECRET", "\"$cfSecret\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    // Persistent upload queue.
    val room = "2.6.1"
    implementation("androidx.room:room-runtime:$room")
    implementation("androidx.room:room-ktx:$room")
    ksp("androidx.room:room-compiler:$room")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
