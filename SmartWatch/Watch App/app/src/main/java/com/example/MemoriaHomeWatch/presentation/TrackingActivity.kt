package com.example.MemoriaHomeWatch.presentation

import android.hardware.Sensor
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
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.lifecycle.lifecycleScope
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.Scaffold
import androidx.wear.compose.material.Text
import androidx.wear.tooling.preview.devices.WearDevices
import com.example.MemoriaHomeWatch.BuildConfig
import com.example.MemoriaHomeWatch.presentation.MainActivity.Companion.mqtt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch


class TrackingActivity : ComponentActivity() {

    companion object { // companion objects can be referenced from another class
        const val TAG = "TrackActivityy"

        // handles data from the PassiveMonitoringClient in HealthServiceManager (google's Health Service API)
        fun dataHandlePassive(data: DataPointContainer){
            val heartRatePoints = data.getData(DataType.HEART_RATE_BPM)
            if (heartRatePoints.isNotEmpty()) {
                val latest = heartRatePoints.last()

                Log.d(TAG, "HEART_RATE_BPM: ${latest.value}")

                val hrValue = latest.value
                Log.d(TAG, "HEART_RATE_BPM: $hrValue")

                try {
                    mqtt.publish("watch-data", hrValue.toString(), 1)
                } catch (e: Exception) {
                    Log.d("MQTT", "Publish failed: ${e.message}")
                    if (e.message == "Client is not connected"){
                        mqtt.mqttConnect(MainActivity.ipAddress, BuildConfig.MQTT_USERNAME, BuildConfig.MQTT_PASSWORD, false )
                    }
                }
            }
        }
    }
    private var offBodyDebounceJob: kotlinx.coroutines.Job? = null

    private var isTracking by mutableStateOf(false)
    private var activeSensors by mutableStateOf(setOf(""))

    private var heartRate by mutableStateOf("--")
    private var acclrData by mutableStateOf("--")

    lateinit var googleServicesManager: HealthServicesManager // google's
    private lateinit var sensorManager : SensorManagerWrapper // interacts with hardware
    private var offBodySensor : Sensor? = null
    private var isOffBody = false


    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        sensorManager = SensorManagerWrapper(
            context = this,
            onOffBody = { worn ->
                offBodyDebounceJob?.cancel()
                offBodyDebounceJob = lifecycleScope.launch {
                    kotlinx.coroutines.delay(500) // wait 500ms before acting
                    if (worn) {
                        if (isTracking) {
                            googleServicesManager.resumeAllMeasuring()
                            sensorManager.resumeAll()
                            Toast.makeText(this@TrackingActivity, "Watch on", Toast.LENGTH_LONG).show()
                        }
                        heartRate = "--"
                    } else {
                        googleServicesManager.pauseAllMeasuring()
                        sensorManager.pauseAll()
                        heartRate = "Sensor off wrist"
                        lifecycleScope.launch(Dispatchers.IO) {
                            publish("Sensor off wrist", "watch-data")
                        }
                        Toast.makeText(this@TrackingActivity, "Watch removed", Toast.LENGTH_LONG).show()
                    }
                }
            },
            onAcclr = { x, y, z ->
                acclrData = "x:$x \ny:$y \nz:$z"
//                lifecycleScope.launch(Dispatchers.IO) {
//                    publish(acclrData, "watch-data")
//                }
                Log.d(TAG, "Acclr: x=$x, y=$y,z=$z")
            })

        sensorManager.startOffBody()
        googleServicesManager = HealthServicesManager(this)

        setContent {
            MaterialTheme {
                TrackAppUi(
                    onToggle = { stopButtonClicked() },
                    onToggleHR = {
                        if (activeSensors.contains("HR")) {
                            googleServicesManager.stopMeasuring(DataType.HEART_RATE_BPM)
                            lifecycleScope.launch(Dispatchers.IO) {
                                publish("Monitoring stopped", "watch-data")
                            }
                            activeSensors = activeSensors - "HR"
                            heartRate = "--"
                        } else {
                            if(isTracking && sensorManager.isWorn) {
                                googleServicesManager.startMeasuring(DataType.HEART_RATE_BPM) { type, data -> dataHandleMeassure(type, data) }
                                activeSensors = activeSensors + "HR"
                            }
                        }
                    },
                    onToggleAcclr = {
                        if(activeSensors.contains("Acclr")){
                            sensorManager.stopAcclr()
                            activeSensors = activeSensors - "Acclr"
                            acclrData = "--"
                        } else {
                            if(isTracking && sensorManager.isWorn) {
                                sensorManager.startAcclr()
                                activeSensors = activeSensors + "Acclr"
                            }
                        }
                    },
                    isTracking = isTracking,
                    heartRate = heartRate,
                    acclrData = acclrData,
                    activeSensors = activeSensors
                )
            }
        }
    }

    private fun stopButtonClicked(){
        if(isTracking){
            sensorManager.pauseAll()
            googleServicesManager.pauseAllMeasuring()
            lifecycleScope.launch(Dispatchers.IO) {
                publish("Monitoring paused", "watch-data")
            }
            isTracking = false
        } else {
            googleServicesManager.resumeAllMeasuring()
            if (sensorManager.isWorn) sensorManager.resumeAll()
            mqtt.mqttConnect(MainActivity.ipAddress, BuildConfig.MQTT_USERNAME, BuildConfig.MQTT_PASSWORD, false )
            isTracking = true
        }
    }

    // handles data from the MeasureClient in HealthServiceManager (google's Health Service API)
    private fun dataHandleMeassure(type: DataType<*, *>, data: DataPointContainer){
        when (type){
            DataType.HEART_RATE_BPM -> {
                val latest = data.getData(DataType.HEART_RATE_BPM).lastOrNull()
                if (latest != null && latest.value > 0) {
                    heartRate = latest.value.toInt().toString()
                    Log.d(TAG, "HEART_RATE_BPM: ${latest.value}")
                    lifecycleScope.launch(Dispatchers.IO) {
                        publish(heartRate, "watch-data")
                    }
                }
            }
        }
    }

    private fun publish(data: String, topic: String){
        try {
            mqtt.publish(topic, data, 1)
        } catch (e: Exception) {
            Log.e("MQTT", "Publish failed: ${e.message}")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "TrackingActivity Destroyed")
        sensorManager.stopAll()
        googleServicesManager.resetAllMeasuring()
//        googleServicesManager.stopPassiveCallback()
//        googleServicesManager.stopPassiveService()
    }
}

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
                top = 0.dp
                ,
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
            item{
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
                        text = if (isTracking) "Pause All" else "Start Tracking",
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