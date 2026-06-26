package com.example.MemoriaHomeWatch.presentation

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import com.example.MemoriaHomeWatch.BuildConfig

class StartupReceiver : BroadcastReceiver() {
    override fun onReceive(p0: Context, p1: Intent) {
        if (p1.action != Intent.ACTION_BOOT_COMPLETED) return
        WorkManager.getInstance(p0).enqueue(
            OneTimeWorkRequestBuilder<RegisterForPassiveDataWorker>().build()
        )
    }
}

class RegisterForPassiveDataWorker(
    private val appContext: Context,
    workerParams: WorkerParameters
) : Worker(appContext, workerParams) {

    companion object {
        private const val TAG = "RegisterForPassiveDataWorker"
    }

    // FIX: own MQTTManager instance instead of depending on MainActivity.mqtt,
    // which doesn't exist yet right after a reboot.
    private val mqttManager = MQTTManager { /* no incoming-message handling needed here */ }

    override fun doWork(): Result {
        return try {
            mqttManager.mqttConnect(
                BuildConfig.MQTT_BROKER,
                BuildConfig.MQTT_USERNAME,
                BuildConfig.MQTT_PASSWORD,
                false
            )

            HealthServicesManager(appContext).startPassiveMonitoring(
                setOf(DataType.HEART_RATE_BPM),
                { data -> handlePassiveData(data) },
                false
            )

            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to register for passive data on boot: ${e.message}")
            Result.failure()
        }
    }

    private fun handlePassiveData(data: DataPointContainer) {
        val heartRatePoints = data.getData(DataType.HEART_RATE_BPM)
        val latest = heartRatePoints.lastOrNull() ?: return
        Log.d(TAG, "Boot passive HEART_RATE_BPM: ${latest.value}")
        try {
            // FIX: same structured JSON schema used elsewhere, instead of a bare value.
            val payload = """{"type":"heart_rate","value":${latest.value},"timestamp":${System.currentTimeMillis()}}"""
            mqttManager.publish("watch-data", payload, 1)
        } catch (e: Exception) {
            Log.e(TAG, "Publish failed: ${e.message}")
        }
    }
}