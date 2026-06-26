package com.example.MemoriaHomeWatch.presentation

import android.app.ActivityManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.Scaffold
import androidx.wear.compose.material.Text
import androidx.wear.tooling.preview.devices.WearDevices
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class TrackingActivity : ComponentActivity() {

    companion object {
        const val TAG = "TrackingActivity"
    }

    private var isTracking by mutableStateOf(false)
    private var activeSensors by mutableStateOf(setOf<String>())
    private var heartRate by mutableStateOf("--")
    private var acclrData by mutableStateOf("--")

    private lateinit var sensorManager: SensorManagerWrapper
    private var offBodyDebounceJob: kotlinx.coroutines.Job? = null

    private val vitalsReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == ForegroundService.ACTION_VITALS_UPDATE) {
                val hr = intent.getIntExtra(ForegroundService.EXTRA_HEART_RATE, 0)
                if (hr > 0) {
                    heartRate = hr.toString()
                    Log.d(TAG, "Received HR from ForegroundService: $hr")
                }
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Lifecycle
    // ─────────────────────────────────────────────────────────────────────────

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        isTracking = isServiceRunning()
        if (isTracking) activeSensors = setOf("HR")

        if (intent?.getBooleanExtra("samsung_sdk_resolution", false) == true) {
            Log.d(TAG, "Handling Samsung SDK resolution")
        }

        setupSensorManager()

        setContent {
            MaterialTheme {
                TrackAppUi(
                    onToggle = { toggleTracking() },
                    onToggleHR = { toggleSensor("HR") },
                    onToggleAcclr = { toggleSensor("Acclr") },
                    isTracking = isTracking,
                    heartRate = heartRate,
                    acclrData = acclrData,
                    activeSensors = activeSensors
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        LocalBroadcastManager.getInstance(this).registerReceiver(
            vitalsReceiver,
            IntentFilter(ForegroundService.ACTION_VITALS_UPDATE)
        )
        Log.d(TAG, "Registered vitals broadcast receiver")
    }

    override fun onPause() {
        super.onPause()
        LocalBroadcastManager.getInstance(this).unregisterReceiver(vitalsReceiver)
        Log.d(TAG, "Unregistered vitals broadcast receiver")
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "TrackingActivity onDestroy")
        if (::sensorManager.isInitialized) {
            sensorManager.stopAll()
        }
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Sensor Setup
    // ─────────────────────────────────────────────────────────────────────────

    private fun setupSensorManager() {
        sensorManager = SensorManagerWrapper(
            context = this,
            onOffBody = { worn ->
                offBodyDebounceJob?.cancel()
                offBodyDebounceJob = lifecycleScope.launch {
                    delay(500)
                    if (worn) {
                        heartRate = "--"
                        Toast.makeText(this@TrackingActivity, "Watch on", Toast.LENGTH_SHORT).show()
                    } else {
                        heartRate = "Off wrist"
                        Toast.makeText(this@TrackingActivity, "Watch removed", Toast.LENGTH_SHORT).show()
                    }
                    Log.d(TAG, "Off-body state changed — worn: $worn")
                }
            },
            onAcclr = { x, y, z ->
                if (activeSensors.contains("Acclr")) {
                    acclrData = "x:$x \ny:$y \nz:$z"
                }
                Log.d(TAG, "Acclr: x=$x, y=$y, z=$z")
            }
        )
        sensorManager.startOffBody()
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Tracking Control
    // ─────────────────────────────────────────────────────────────────────────

    private fun toggleTracking() {
        if (isTracking) {
            ForegroundService.userStopped = true

            if (activeSensors.contains("Acclr")) {
                sensorManager.stopAcclr()
                Log.d(TAG, "Accelerometer stopped on tracking stop")
            }

            // FIX: Instead of stopService() from outside (unreliable for foreground
            // services on Wear OS), send an explicit stop action so the service
            // calls stopForeground() + stopSelf() on itself — the only guaranteed way
            val stopIntent = Intent(this, ForegroundService::class.java).apply {
                action = ForegroundService.ACTION_STOP_SERVICE
            }
            startService(stopIntent)

            isTracking = false
            activeSensors = emptySet()
            heartRate = "--"
            acclrData = "--"
            Log.d(TAG, "Tracking stopped — stop intent sent to ForegroundService")
        } else {
            startForegroundService(Intent(this, ForegroundService::class.java))
            isTracking = true
            activeSensors = setOf("HR")
            Log.d(TAG, "Tracking started — ForegroundService started")
        }
    }

    private fun toggleSensor(sensor: String) {
        activeSensors = if (activeSensors.contains(sensor)) {
            activeSensors - sensor
        } else {
            activeSensors + sensor
        }

        if (sensor == "Acclr") {
            if (activeSensors.contains("Acclr")) {
                sensorManager.startAcclr()
                Log.d(TAG, "Accelerometer enabled")
            } else {
                sensorManager.stopAcclr()
                acclrData = "--"
                Log.d(TAG, "Accelerometer disabled")
            }
        }

        Log.d(TAG, "Active sensors: $activeSensors")
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────────────────────────────────

    @Suppress("DEPRECATION")
    private fun isServiceRunning(): Boolean {
        val manager = getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        return manager.getRunningServices(Int.MAX_VALUE)
            .any { it.service.className == ForegroundService::class.java.name }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Composable UI
// ─────────────────────────────────────────────────────────────────────────────

@Composable
fun TrackAppUi(
    onToggle: () -> Unit,
    onToggleHR: () -> Unit,
    onToggleAcclr: () -> Unit,
    isTracking: Boolean,
    heartRate: String,
    acclrData: String,
    activeSensors: Set<String>
) {
    val hrActive = activeSensors.contains("HR")
    val acclrActive = activeSensors.contains("Acclr")

    Scaffold {
        androidx.wear.compose.foundation.lazy.ScalingLazyColumn(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            contentPadding = androidx.compose.foundation.layout.PaddingValues(
                top = 0.dp,
                bottom = 16.dp,
                start = 8.dp,
                end = 8.dp
            ),
            scalingParams = androidx.wear.compose.foundation.lazy.ScalingLazyColumnDefaults.scalingParams(
                minTransitionArea = 0f,
                maxTransitionArea = 0f
            )
        ) {
            item {
                Text(
                    text = "Active Sensors",
                    style = MaterialTheme.typography.caption2,
                    textAlign = TextAlign.Center,
                    color = androidx.compose.ui.graphics.Color.Gray
                )
            }
            item {
                androidx.compose.foundation.layout.Column(
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    if (!hrActive && !acclrActive) {
                        Text(
                            text = "None",
                            style = MaterialTheme.typography.caption2,
                            textAlign = TextAlign.Center,
                            color = androidx.compose.ui.graphics.Color.DarkGray
                        )
                    }
                    if (hrActive) {
                        Text(
                            text = "Heart Rate",
                            style = MaterialTheme.typography.caption2,
                            textAlign = TextAlign.Center,
                            color = androidx.compose.ui.graphics.Color.LightGray
                        )
                        Text(
                            text = "${heartRate}bpm",
                            style = MaterialTheme.typography.caption3,
                            textAlign = TextAlign.Center,
                            color = androidx.compose.ui.graphics.Color.Gray
                        )
                    }
                    if (hrActive && acclrActive) {
                        androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(4.dp))
                    }
                    if (acclrActive) {
                        Text(
                            text = "Accelerometer",
                            style = MaterialTheme.typography.caption2,
                            textAlign = TextAlign.Center,
                            color = androidx.compose.ui.graphics.Color.LightGray
                        )
                        Text(
                            text = acclrData,
                            style = MaterialTheme.typography.caption3,
                            textAlign = TextAlign.Center,
                            color = androidx.compose.ui.graphics.Color.Gray
                        )
                    }
                }
            }
            item {
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(5.dp))
            }
            item {
                Button(
                    onClick = onToggle,
                    modifier = Modifier
                        .fillMaxWidth(0.7f)
                        .height(36.dp),
                    colors = androidx.wear.compose.material.ButtonDefaults.buttonColors(
                        backgroundColor = if (isTracking)
                            androidx.compose.ui.graphics.Color(0xFFB71C1C)
                        else
                            androidx.compose.ui.graphics.Color(0xFF1B5E20)
                    )
                ) {
                    Text(
                        text = if (isTracking) "Stop Monitoring" else "Start Monitoring",
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.caption1
                    )
                }
            }
            item {
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(4.dp))
                Button(
                    onClick = onToggleHR,
                    modifier = Modifier
                        .fillMaxWidth(0.5f)
                        .height(20.dp),
                    colors = androidx.wear.compose.material.ButtonDefaults.buttonColors(
                        backgroundColor = androidx.compose.ui.graphics.Color(0xFF424242)
                    )
                ) {
                    Text(
                        text = "Heart Rate",
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.caption2,
                        color = if (hrActive)
                            androidx.compose.ui.graphics.Color.White
                        else
                            androidx.compose.ui.graphics.Color.Gray
                    )
                }
            }
            item {
                androidx.compose.foundation.layout.Spacer(modifier = Modifier.size(4.dp))
                Button(
                    onClick = onToggleAcclr,
                    modifier = Modifier
                        .fillMaxWidth(0.5f)
                        .height(20.dp),
                    colors = androidx.wear.compose.material.ButtonDefaults.buttonColors(
                        backgroundColor = androidx.compose.ui.graphics.Color(0xFF424242)
                    )
                ) {
                    Text(
                        text = "Accelerometer",
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.caption2,
                        color = if (acclrActive)
                            androidx.compose.ui.graphics.Color.White
                        else
                            androidx.compose.ui.graphics.Color.Gray
                    )
                }
            }
        }
    }
}

@Preview(
    device = WearDevices.SMALL_ROUND,
    showSystemUi = true,
    backgroundColor = 0xff000000,
    showBackground = true
)
@Composable
fun TrackingActivityPreview() {
    MaterialTheme {
        TrackAppUi(
            onToggle = {},
            onToggleHR = {},
            onToggleAcclr = {},
            isTracking = true,
            heartRate = "72",
            acclrData = "x:0.1 y:9.8 z:0.3",
            activeSensors = setOf("HR", "Acclr")
        )
    }
}