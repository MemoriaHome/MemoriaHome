package com.example.MemoriaHomeWatch.presentation

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

class StartupReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "StartupReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return

        Log.d(TAG, "Boot completed — starting ForegroundService")

        // Directly start the ForegroundService which handles everything:
        // wake-up HR sensor, Samsung SDK, Google Health Services, MQTT, WakeLock
        context.startForegroundService(
            Intent(context, ForegroundService::class.java)
        )
    }
}