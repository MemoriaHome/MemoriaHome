package com.example.MemoriaHomeWatch.presentation

import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
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
import com.example.MemoriaHomeWatch.presentation.MainActivity.Companion.mqtt
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.android.service.health.tracking.data.ValueKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch


class TrackingActivity : ComponentActivity(), SensorEventListener {

    companion object { // companion objects can be referenced from another class
        val TAG = "TrackActivityy"

        // handles data from the PasswiveMonitoringClient in HealthServiceManager (google's Health Service API)
        fun dataHandlePassive(data: DataPointContainer){
            val heartRatePoints = data.getData(DataType.HEART_RATE_BPM)
            if (heartRatePoints.isNotEmpty()) {
                val latest = heartRatePoints.last()
                Log.d(TAG, "HEART_RATE_BPM: ${latest.value}")
            }
            // Handle other data types as needed
        }
    }
//    private var isTrackingBPM = false
//    private var isTrakingAcclr = false
    private var buttontext by mutableStateOf("Restart Tracking")
    private var isTracking by mutableStateOf(false)

    lateinit var healthSDKManager: HealthSDKManager // samsung's
    lateinit var healthServicesManager: HealthServicesManager // google's
    private lateinit var mSensorManager : SensorManager // interacts with hardware
    private var offBodySensor : Sensor? = null


    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        healthSDKManager = HealthSDKManager(this,      ///// initialize samsung's Health Tracking SDK
            {startTracking()},
            {it.resolve(this)},
            {type, p0 -> dataHandleSDK(type, p0)})

        healthSDKManager.connect()
        healthSDKManager.startTracker(HealthTrackerType.HEART_RATE_CONTINUOUS)
//        healthSDKManager.startTracker(HealthTrackerType.ACCELEROMETER_CONTINUOUS)


//        healthServicesManager = HealthServicesManager(this)      ///// initialize google's Health Service
//        healthServicesManager.startPassiveMonitoring(setOf(DataType.HEART_RATE_BPM), {data -> dataHandlePassive(data)}, false)

        setContent {
            MaterialTheme {
                TrackAppUi(onExit = {buttonClicked()}, buttontext)
            }
        }
    }


    // handles data from the HealthSDKManager (Samsung's Health Tracking SDK)
    private fun dataHandleSDK(type: HealthTrackerType, p0: List<DataPoint?>) {
        lifecycleScope.launch(Dispatchers.IO) {
            for (data in p0) {
                data ?: continue

                when (type){
                    HealthTrackerType.HEART_RATE_CONTINUOUS -> {
                        val hrData = data.getValue(ValueKey.HeartRateSet.HEART_RATE)
                        Log.d(TAG, "Sending messages...")
                        launch {
                            try {
                                mqtt.publish("watch-data", hrData.toString(), 1)
                            } catch (e: Exception) {
                                Log.e("MQTT", "Publish failed: ${e.message}")
                            }
                        }
                        Log.d(TAG, "Heart Rate: $hrData")
                    }

                    HealthTrackerType.ACCELEROMETER_CONTINUOUS -> {
                        val accelDataX = data.getValue(ValueKey.AccelerometerSet.ACCELEROMETER_X)
                        val accelDataY = data.getValue(ValueKey.AccelerometerSet.ACCELEROMETER_Y)
                        val accelDataZ = data.getValue(ValueKey.AccelerometerSet.ACCELEROMETER_Z)

                        launch {
                            try {
                                var payload = "{\\\"x\\\":$accelDataX, \\\"y\\\":$accelDataY, \\\"z\\\":$accelDataZ}"
                                mqtt.publish("watch-data", payload, 1)
                            } catch (e: Exception) {
                                Log.e("MQTT", "Publish failed: ${e.message}")
                            }
                        }

                        Log.d(TAG, "Accelerometer X: $accelDataX, Y: $accelDataY, Z: $accelDataZ")
                    }
                    else -> { }
                }
            }
        }
    }

    // handles data from the MeasureClient in HealthServiceManager (google's Health Service API) i think we can combine it with the dataHandlePassive() later
    fun dataHandleMeassure(type: DataType<*, *>, data: DataPointContainer){
        when (type){
            DataType.HEART_RATE_BPM -> {
                val heartRatePoints = data.getData(DataType.HEART_RATE_BPM)
                if (heartRatePoints.isNotEmpty()) {
                    val latest = heartRatePoints.last()
                    Log.d(TAG, "HEART_RATE_BPM: ${latest.value}")
                } else {
                    Log.d(TAG, "No heart rate data received")
                }
            }
            else -> {
                // Handle other data types as needed
                Log.d(TAG, "No heart rate data received")
            }
        }
    }



    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "TrackingActivity Destroyed")
        if(::mSensorManager.isInitialized){ mSensorManager.unregisterListener(this); }
        //healthSDKManager.disconnect()
    }

    override fun onAccuracyChanged(p0: Sensor?, p1: Int) {
        //
    }

    override fun onSensorChanged(p0: SensorEvent?) {
        val offBodyDataFloat = p0?.values[0]
        val offBodyData = offBodyDataFloat?.toInt()
        if (offBodyData == 1){
            Log.d(TAG, "Watch is being worn")
            //healthSDKManager.resumeAllTrackers()
        } else {
            Log.d(TAG, "Watch is NOT being worn")
            Toast.makeText(this, "Watch removed",Toast.LENGTH_LONG).show()
            //healthSDKManager.pauseAllTrackers()
        }
    }

    private fun startOffBodySensor(){
        mSensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
        offBodySensor = mSensorManager.getDefaultSensor(Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT)
        mSensorManager.registerListener(this, offBodySensor, SensorManager.SENSOR_DELAY_NORMAL)
    }

    private fun startTracking() {
        startOffBodySensor()
        //healthSDKManager.startTracker(HealthTrackerType.ACCELEROMETER_CONTINUOUS)
        //healthSDKManager.startTracker(HealthTrackerType.HEART_RATE_CONTINUOUS)
        buttontext = "Stop Tracking"
        isTracking = true
    }

    private fun buttonClicked(){
        if(isTracking){
            if(::mSensorManager.isInitialized){ mSensorManager.unregisterListener(this); }
            //healthSDKManager.pauseAllTrackers()
            buttontext = "Start Tracking"
            isTracking = false
        } else {
            startOffBodySensor()
            //healthSDKManager.resumeAllTrackers()
            buttontext = "Stop Tracking"
            isTracking = true
        }
    }
}

@Composable
fun TrackAppUi(onExit: () -> Unit, buttontext: String) {
    Scaffold {
        Box(
            modifier = Modifier.fillMaxSize(),
            contentAlignment = Alignment.Center
        ) {
            Button(onClick = onExit, modifier = Modifier.size(100.dp)) {
                Text(
                    text = buttontext,
                    textAlign = TextAlign.Center)
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
        TrackAppUi(onExit = {}, buttontext = "Restart Tracking")
    }
}
