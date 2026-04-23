package com.example.MemoriaHomeWatch.presentation

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorManager
import android.hardware.SensorEventListener
import android.util.Log

class SensorManagerWrapper(
    context: Context,
    private val onOffBody: (Boolean) -> Unit,
    private val onAcclr: (Float, Float, Float) -> Unit
) : SensorEventListener {

    private val TAG = "SensorManagerWrapper"
    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private var offBodySensor: Sensor? = null
    private var accelerometer: Sensor? = null
    private var acclrActive = false
    var isWorn = false

    fun startOffBody() {
        offBodySensor = sensorManager.getDefaultSensor(Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT)
        sensorManager.registerListener(this, offBodySensor, SensorManager.SENSOR_DELAY_NORMAL)
        Log.d(TAG, "Off-body sensor started")
    }

    fun startAcclr() {
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        sensorManager.registerListener(this, accelerometer, SensorManager.SENSOR_DELAY_NORMAL)
        acclrActive = true
        Log.d(TAG, "Accelerometer started")
    }

    fun stopAcclr() {
        sensorManager.unregisterListener(this, accelerometer)
        acclrActive = false
        Log.d(TAG, "Accelerometer stopped")
    }

    fun pauseAll() {
        sensorManager.unregisterListener(this, accelerometer)
        Log.d(TAG, "All sensors paused")
    }

    fun resumeAll() {
        if (acclrActive && isWorn) startAcclr()
        Log.d(TAG, "All sensors resumed")
    }

    fun stopAll() {
        sensorManager.unregisterListener(this)
        Log.d(TAG, "All sensors stopped")
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    override fun onSensorChanged(event: SensorEvent?) {
        when (event?.sensor?.type) {
            Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT -> {
                val worn = event.values[0].toInt() == 1
                isWorn = worn
                Log.d(TAG, if (worn) "Watch is being worn" else "Watch is NOT being worn")
                onOffBody(worn)
            }
            Sensor.TYPE_ACCELEROMETER -> {
                onAcclr(event.values[0], event.values[1], event.values[2])
            }
        }
    }
}