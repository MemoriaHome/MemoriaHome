package com.example.MemoriaHomeWatch.presentation

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import com.example.MemoriaHomeWatch.BuildConfig
import com.example.MemoriaHomeWatch.R
import com.samsung.android.service.health.tracking.HealthTrackerException
import com.samsung.android.service.health.tracking.data.DataPoint
import com.samsung.android.service.health.tracking.data.HealthTrackerType
import com.samsung.android.service.health.tracking.data.ValueKey
import kotlinx.coroutines.*

class ForegroundService : Service(), SensorEventListener {

    companion object {
        private const val CHANNEL_ID = "vitals_tracking_channel"
        private const val CHANNEL_NAME = "Vitals Tracking"
        private const val NOTIFICATION_ID = 100
        private const val TAG = "ForegroundService"

        const val ACTION_VITALS_UPDATE = "com.example.MemoriaHomeWatch.VITALS_UPDATE"
        const val EXTRA_HEART_RATE = "heart_rate"
        const val EXTRA_SPO2 = "spo2"
        const val EXTRA_TIMESTAMP = "timestamp"

        // FIX: explicit stop action — calling stopService() from outside isn't
        // reliably honored by Wear OS once a foreground service is promoted.
        const val ACTION_STOP_SERVICE = "com.example.MemoriaHomeWatch.ACTION_STOP_SERVICE"
        var userStopped = false

        // FIX: holds the pending Samsung SDK exception so TrackingActivity (which has
        // an Activity context) can call resolve() on it — the Service can't.
        var pendingHealthException: HealthTrackerException? = null
    }

    private lateinit var healthSDKManager: HealthSDKManager
    private lateinit var healthServicesManager: HealthServicesManager

    private lateinit var sensorManager: SensorManager
    private var offBodySensor: Sensor? = null
    private var isWatchWorn = true

    private var currentHeartRate = 0
    private var currentSpO2 = 0f

    private lateinit var mqttManager: MQTTManager

    private lateinit var serviceHandler: Handler
    private lateinit var handlerThread: HandlerThread
    private val coroutineScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    private var wakeLock: PowerManager.WakeLock? = null

    private var lastMqttPublishTime = 0L
    private val MQTT_PUBLISH_INTERVAL = 2000L

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Service onCreate")
        userStopped = false

        initializeManagers()
        setupBackgroundThread()
        setupWakeLock()
        createNotificationChannel()
        startForegroundService()
        startVitalsTracking()
        startOffBodyDetection()
    }

    private fun initializeManagers() {
        mqttManager = MQTTManager { message ->
            Log.d(TAG, "MQTT message received: $message")
        }
        connectMQTT()

        healthSDKManager = HealthSDKManager(
            this,
            onConnected = {
                Log.d(TAG, "Samsung Health SDK connected")
                startSamsungTracking()
            },
            onResolution = { exception ->
                Log.e(TAG, "Samsung SDK resolution needed", exception)
                // FIX: HealthTrackerException.resolve() requires an Activity — store
                // the exception and hand resolution off to TrackingActivity instead
                // of calling exception.resolve(this) on a Service (type mismatch).
                pendingHealthException = exception
                val resolutionIntent = Intent(this, TrackingActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                    putExtra("samsung_sdk_resolution", true)
                }
                startActivity(resolutionIntent)
            },
            dataReceived = { type, dataPoints ->
                handleSamsungData(type, dataPoints)
            }
        )

        healthServicesManager = HealthServicesManager(this)
        healthSDKManager.connect()
        startGooglePassiveMonitoring()
    }

    private fun connectMQTT() {
        coroutineScope.launch {
            try {
                mqttManager.mqttConnect(
                    BuildConfig.MQTT_BROKER,
                    BuildConfig.MQTT_USERNAME,
                    BuildConfig.MQTT_PASSWORD,
                    false
                )
                Log.d(TAG, "MQTT Connected")
            } catch (e: Exception) {
                Log.e(TAG, "MQTT Connection failed", e)
            }
        }
    }

    private fun startGooglePassiveMonitoring() {
        try {
            healthServicesManager.startPassiveMonitoring(
                setOf(DataType.HEART_RATE_BPM),
                { dataPointContainer -> handleGooglePassiveData(dataPointContainer) },
                false
            )
            Log.d(TAG, "Google passive monitoring started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Google passive monitoring", e)
        }
    }

    private fun startSamsungTracking() {
        try {
            healthSDKManager.startTracker(HealthTrackerType.HEART_RATE_CONTINUOUS)
            Log.d(TAG, "Samsung heart rate tracking started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start Samsung tracking", e)
        }
    }

    private fun handleSamsungData(type: HealthTrackerType, dataPoints: List<DataPoint?>) {
        coroutineScope.launch {
            for (data in dataPoints) {
                data ?: continue
                when (type) {
                    HealthTrackerType.HEART_RATE_CONTINUOUS -> {
                        val heartRate = data.getValue(ValueKey.HeartRateSet.HEART_RATE)
                        if (heartRate > 0) {
                            currentHeartRate = heartRate
                            Log.d(TAG, "Samsung HR: $heartRate")
                            publishToMQTT("heart_rate", heartRate.toString())
                            updateNotification()
                            broadcastToUI()
                        }
                    }
                    else -> {}
                }
            }
        }
    }

    private fun handleGooglePassiveData(data: DataPointContainer) {
        coroutineScope.launch {
            val heartRatePoints = data.getData(DataType.HEART_RATE_BPM)
            if (heartRatePoints.isNotEmpty()) {
                val latest = heartRatePoints.last()
                val heartRate = latest.value.toInt()
                if (heartRate > 0) {
                    currentHeartRate = heartRate
                    Log.d(TAG, "Google HR: $heartRate")
                    publishToMQTT("heart_rate", heartRate.toString())
                    updateNotification()
                    broadcastToUI()
                }
            }
        }
    }

    private fun publishToMQTT(topic: String, value: String) {
        val currentTime = System.currentTimeMillis()
        if (currentTime - lastMqttPublishTime >= MQTT_PUBLISH_INTERVAL) {
            lastMqttPublishTime = currentTime
            coroutineScope.launch {
                try {
                    val payload = """{"type":"$topic","value":$value,"timestamp":$currentTime,"watchWorn":$isWatchWorn}"""
                    mqttManager.publish("watch-data", payload, 1)
                    Log.d(TAG, "MQTT Published: $payload")
                } catch (e: Exception) {
                    Log.e(TAG, "MQTT Publish failed", e)
                    if (e.message?.contains("not connected") == true) {
                        connectMQTT()
                    }
                }
            }
        }
    }

    private fun updateNotification() {
        val notificationIntent = Intent(this, TrackingActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, notificationIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Memoria Home - Monitoring Active")
            .setContentText("$currentHeartRate BPM | Status: ${if (isWatchWorn) "Worn" else "Off"}")
            .setSmallIcon(R.drawable.ic_heart_rate)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .setContentIntent(pendingIntent)
            .build()

        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            notification,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
            } else {
                0
            }
        )
    }

    private fun broadcastToUI() {
        val intent = Intent(ACTION_VITALS_UPDATE).apply {
            putExtra(EXTRA_HEART_RATE, currentHeartRate)
            putExtra(EXTRA_SPO2, currentSpO2)
            putExtra(EXTRA_TIMESTAMP, System.currentTimeMillis())
        }
        // FIX: LocalBroadcastManager keeps this inside the app instead of system-wide.
        LocalBroadcastManager.getInstance(this).sendBroadcast(intent)
    }

    private fun startOffBodyDetection() {
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        offBodySensor = sensorManager.getDefaultSensor(Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT)

        offBodySensor?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
            Log.d(TAG, "Off-body detection started")
        } ?: Log.w(TAG, "Off-body sensor not available")
    }

    override fun onSensorChanged(event: SensorEvent?) {
        event?.let {
            if (it.sensor.type == Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT) {
                val wasWorn = isWatchWorn
                isWatchWorn = it.values[0].toInt() == 1

                if (wasWorn != isWatchWorn) {
                    Log.d(TAG, "Watch wear state changed: ${if (isWatchWorn) "Worn" else "Not worn"}")

                    if (isWatchWorn) {
                        healthSDKManager.resumeAllTrackers()
                        startGooglePassiveMonitoring()
                    } else {
                        healthSDKManager.pauseAllTrackers()
                        healthServicesManager.stopPassiveCallback()
                    }
                    updateNotification()
                }
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    private fun setupBackgroundThread() {
        handlerThread = HandlerThread("VitalsServiceThread").apply {
            start()
        }
        serviceHandler = Handler(handlerThread.looper)
    }

    private fun setupWakeLock() {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "MemoriaHome:VitalsWakeLock"
        ).apply {
            setReferenceCounted(false)
            // FIX: indefinite acquisition — a 30-minute timeout contradicted the
            // stated goal of continuous 24/7 monitoring. Released in onDestroy().
            acquire()
        }
        Log.d(TAG, "WakeLock acquired indefinitely")
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Continuous vitals tracking"
                setShowBadge(false)
            }

            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun startForegroundService() {
        try {
            val notification = NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Memoria Home")
                .setContentText("Starting vitals monitoring...")
                .setSmallIcon(R.drawable.ic_heart_rate)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build()

            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
                } else {
                    0
                }
            )
            Log.d(TAG, "Foreground service started")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start foreground service", e)
        }
    }

    private fun startVitalsTracking() {
        Log.d(TAG, "Vitals tracking started")
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // FIX: handle explicit stop action — the service stops itself via
        // stopForeground()+stopSelf(), which Wear OS honors more reliably than
        // an external stopService() call.
        if (intent?.action == ACTION_STOP_SERVICE) {
            Log.d(TAG, "Stop action received — shutting down cleanly")
            userStopped = true
            @Suppress("DEPRECATION")
            stopForeground(true)
            stopSelf()
            return START_NOT_STICKY
        }
        Log.d(TAG, "onStartCommand called")
        // FIX: START_NOT_STICKY — START_STICKY would let the OS silently
        // recreate this service after being killed, even post-stop.
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d(TAG, "Service onDestroy")

        sensorManager.unregisterListener(this)
        healthSDKManager.disconnect()
        healthServicesManager.stopPassiveCallback()
        healthServicesManager.stopPassiveService()
        handlerThread.quitSafely()
        wakeLock?.release()
        coroutineScope.cancel()
    }
}