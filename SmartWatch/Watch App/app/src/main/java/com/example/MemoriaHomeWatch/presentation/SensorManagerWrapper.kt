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
    private val onAcclr: (Float, Float, Float) -> Unit,
    private val onGyro: (Float, Float, Float) -> Unit
) : SensorEventListener {

    private val TAG = "SensorManagerWrapper"
    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager

    private var offBodySensor: Sensor? = null
    private var accelerometer: Sensor? = null
    private var gyroscope: Sensor? = null

    private var acclrActive = false
    private var gyroActive = false

    // FIX: default to true. If a device has no off-body sensor, onSensorChanged()
    // for TYPE_LOW_LATENCY_OFFBODY_DETECT never fires, so isWorn would otherwise stay
    // false forever — permanently blocking every sensor toggle in TrackingActivity,
    // which requires isWorn==true before letting HR/Accl/Gyro start.
    var isWorn = true

    fun startOffBody() {
        offBodySensor = sensorManager.getDefaultSensor(Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT)
        // FIX: null-check before registering — passing a null Sensor into
        // registerListener() can crash on devices without this hardware.
        offBodySensor?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
            Log.d(TAG, "Off-body sensor started")
        } ?: run {
            isWorn = true
            Log.w(TAG, "Off-body sensor not available on this device — defaulting isWorn=true")
        }
    }

    fun startAcclr() {
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        accelerometer?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
            acclrActive = true
            Log.d(TAG, "Accelerometer started")
        } ?: Log.w(TAG, "Accelerometer not available on this device")
    }

    fun stopAcclr() {
        // FIX: null-check — unregisterListener(this, null) is unsafe if startAcclr()
        // was never successfully called (e.g. sensor missing).
        accelerometer?.let { sensorManager.unregisterListener(this, it) }
        acclrActive = false
        Log.d(TAG, "Accelerometer stopped")
    }

    fun startGyro() {
        gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
        gyroscope?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
            gyroActive = true
            Log.d(TAG, "Gyroscope started")
        } ?: Log.w(TAG, "Gyroscope not available on this device")
    }

    fun stopGyro() {
        gyroscope?.let { sensorManager.unregisterListener(this, it) }
        gyroActive = false
        Log.d(TAG, "Gyroscope stopped")
    }

    fun pauseAll() {
        accelerometer?.let { sensorManager.unregisterListener(this, it) }
        gyroscope?.let { sensorManager.unregisterListener(this, it) }
        Log.d(TAG, "All sensors paused")
    }

    fun resumeAll() {
        if (acclrActive && isWorn) startAcclr()
        if (gyroActive && isWorn) startGyro()
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
            Sensor.TYPE_GYROSCOPE -> {
                onGyro(event.values[0], event.values[1], event.values[2])
            }
        }
    }
}