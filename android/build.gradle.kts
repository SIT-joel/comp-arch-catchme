// Root build file. Versions chosen for compatibility; adjust after opening in
// Android Studio if AGP/Kotlin require updates (no JDK on the authoring
// machine — this project has not been compiled yet, see docs/PROGRESS.md).

plugins {
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.1.0" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0" apply false
    id("com.google.devtools.ksp") version "2.1.0-1.0.29" apply false
}
