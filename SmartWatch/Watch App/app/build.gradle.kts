import org.gradle.kotlin.dsl.implementation
import java.util.Properties

val localProperties = Properties()
val localPropertiesFile = rootProject.file("local.properties")
if (localPropertiesFile.exists()) {
    localProperties.load(localPropertiesFile.inputStream())
}

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.example.MemoriaHomeWatch"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.example.MemoriaHomeWatch"
        minSdk = 30
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"

    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            buildConfigField("String", "MQTT_USERNAME", "\"${localProperties["mqtt.username"]}\"")
            buildConfigField("String", "MQTT_PASSWORD", "\"${localProperties["mqtt.password"]}\"")
            buildConfigField("String", "MQTT_BROKER", "\"${localProperties["mqtt.broker"]}\"")
        }
        debug {
            buildConfigField("String", "MQTT_USERNAME", "\"${localProperties["mqtt.username"]}\"")
            buildConfigField("String", "MQTT_PASSWORD", "\"${localProperties["mqtt.password"]}\"")
            buildConfigField("String", "MQTT_BROKER", "\"${localProperties["mqtt.broker"]}\"")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    kotlinOptions {
        jvmTarget = "11"
    }
    useLibrary("wear-sdk")
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(libs.activity.ktx)
    implementation(libs.appcompat)
    implementation(libs.constraintlayout)
    implementation(libs.material)
    implementation(libs.play.services.wearable)
    implementation(platform(libs.compose.bom))
    implementation(libs.ui)
    implementation(libs.ui.graphics)
    implementation(libs.ui.tooling.preview)
    implementation(libs.compose.material)
    implementation(libs.compose.foundation)
    implementation(libs.wear.tooling.preview)
    implementation(libs.activity.compose)
    implementation(libs.core.splashscreen)
    implementation(libs.lifecycle.runtime.ktx)
    implementation(libs.material3)
    implementation(libs.work.runtime.ktx)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.ui.test.junit4)
    debugImplementation(libs.ui.tooling)
    debugImplementation(libs.ui.test.manifest)

    // paho library
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")

    // Samsung Health Sensor SDK
    implementation(fileTree(mapOf("dir" to "libs", "include" to listOf("*.aar"))))
    // health services
    implementation("androidx.health:health-services-client:1.1.0-beta01")
    // ListenableFuture error
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-guava:1.7.3")
}